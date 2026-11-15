"""
stream.py – UDP-MPEG-TS-Stream (mit optionaler Entschlüsselung am Ende)
=======================================================================
stream             – Tune + UDP-MPEG-TS-Stream (Speicherung der Rohdaten;
                     bei decrypt_after=True wird die Datei am Ende entschlüsselt)
prepare_channel    – Re-Export aus prepare.py
descramble_ts_block, decrypt_ts_file, DEFAULT_TS_KEY – Re-Export aus decrypt.py
"""
from __future__ import annotations

import contextlib
import logging
import socket
import sys
import threading
import time

import protocol
from decrypt import DEFAULT_TS_KEY, decrypt_ts_file, descramble_ts_block
from keepalive import _keepalive_worker
from models import ServiceEntry
from prepare import (
    get_last_prepared_prog_idx,
    prepare_channel,
    reset_prepared_prog_idx,
)

log = logging.getLogger("wisi.stream")

UDP_BLOCK_SIZE: int = protocol.UDP_REQUEST_LEN + 64 + protocol.USBS_LEN  # 48205
SIGNAL_INTVL: float = protocol.SIGNAL_INTVL
UDP_PULL_INTVL: float = 0.5


def stream(
    tcp_sock: socket.socket,
    lock: threading.Lock,
    svc: ServiceEntry,
    output_path: str,
    duration_s: float = 0.0,
    keepalive_active: bool = False,
    decrypt_after: bool = False,
) -> None:
    """
    Tunet (falls noch nicht via prepare_channel geschehen) auf `svc` und schreibt
    MPEG-TS-Daten nach `output_path` ('-' = stdout).

    Wenn `decrypt_after=True` gesetzt ist (CLI `--decrypt`), wird die gespeicherte
    `.ts`-Datei direkt nach Abschluss der Aufnahme entschlüsselt.
    """
    stop = threading.Event()
    dongle_ip = tcp_sock.getpeername()[0]
    tcp_sock_dead = threading.Event()

    ka: threading.Thread | None = None
    if not keepalive_active:
        ka = threading.Thread(
            target=_keepalive_worker,
            args=(tcp_sock, lock, stop, tcp_sock_dead),
            daemon=True,
        )
        ka.start()

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    udp.bind(("", protocol.UDP_PORT))
    udp.settimeout(UDP_PULL_INTVL)

    ts_bytes = 0
    try:
        if get_last_prepared_prog_idx() != svc.prog_idx:
            prepare_channel(tcp_sock, lock, svc)

        # UDP Socket-Init (0xF9/0x02) senden und 13-Byte USBS-Antwort abholen
        udp.sendto(protocol.cmd_udp_init(), (dongle_ip, protocol.UDP_PORT))
        log.debug("0xF9/0x02 UDP-Init gesendet")
        udp.settimeout(0.2)
        try:
            init_ack, _ = udp.recvfrom(65535)
            log.debug("0xF9/0x02 Ack empfangen (%dB)", len(init_ack))
        except TimeoutError:
            pass
        udp.settimeout(UDP_PULL_INTVL)

        log.info("Stream → %s  (STRG+C zum Beenden)", output_path)

        _file_ctx = (
            open(output_path, "wb")  # noqa: SIM115
            if output_path != "-"
            else contextlib.nullcontext(sys.stdout.buffer)
        )
        with _file_ctx as out:
            t_start = time.monotonic()
            block_num = 0
            pull_count = 0
            retry_last = False
            last_seq = -1
            last_packet_at = t_start
            next_timeout_warning = t_start + 5.0
            next_signal_at = t_start + SIGNAL_INTVL

            try:
                while not stop.is_set():
                    now = time.monotonic()
                    if duration_s > 0 and now - t_start >= duration_s:
                        log.info("Dauer %.0f s erreicht.", duration_s)
                        break

                    if now >= next_signal_at and not tcp_sock_dead.is_set():
                        try:
                            with lock:
                                sig = protocol.send_recv(
                                    tcp_sock, protocol.cmd_signal(), 17, "0x02 signal"
                                )
                            if len(sig) >= 5:
                                log.debug("Signal: Stärke=%d%%  Qualität=%d%%", sig[3], sig[4])
                        except OSError:
                            tcp_sock_dead.set()
                        next_signal_at = time.monotonic() + SIGNAL_INTVL

                    udp.sendto(
                        protocol.cmd_udp_ts_block(first=not retry_last),
                        (dongle_ip, protocol.UDP_PORT),
                    )
                    pull_count += 1

                    try:
                        while True:
                            data, _ = udp.recvfrom(65535)
                            if data[:4] == b"USBS" or data[:2] == b"\xf9\x0a":
                                continue
                            break
                    except TimeoutError:
                        retry_last = True
                        time.sleep(0.01)
                        now = time.monotonic()
                        if now >= next_timeout_warning and now - last_packet_at >= 5.0:
                            log.warning(
                                "Seit 5 Sekunden keine UDP-Streamdaten; Pulls laufen weiter."
                            )
                            next_timeout_warning = now + 5.0
                        continue

                    if len(data) < protocol.TS_PKT_SIZE * 4:
                        retry_last = True
                        time.sleep(0.01)
                        continue

                    if len(data) >= protocol.UDP_REQUEST_LEN + 64:
                        seq = data[protocol.UDP_REQUEST_LEN + 12]
                        if last_seq < seq:
                            last_seq = seq
                        elif last_seq == 255:
                            last_seq = 0
                        elif seq == 0:
                            last_seq = -1
                        else:
                            retry_last = True
                            time.sleep(0.01)
                            continue
                        payload = data[:protocol.UDP_REQUEST_LEN]
                    elif len(data) > protocol.UDP_REQUEST_LEN:
                        payload = data[:protocol.UDP_REQUEST_LEN]
                    else:
                        payload = data

                    sync_offset = payload.find(bytes([protocol.TS_SYNC]))
                    while sync_offset >= 0:
                        if (
                            sync_offset + 3 * protocol.TS_PKT_SIZE < len(payload)
                            and all(
                                payload[sync_offset + i * protocol.TS_PKT_SIZE] == protocol.TS_SYNC
                                for i in range(4)
                            )
                        ):
                            break
                        sync_offset = payload.find(bytes([protocol.TS_SYNC]), sync_offset + 1)

                    if sync_offset < 0:
                        retry_last = True
                        time.sleep(0.01)
                        continue

                    ts_data = payload[sync_offset:]
                    complete_len = len(ts_data) - len(ts_data) % protocol.TS_PKT_SIZE
                    if complete_len == 0:
                        retry_last = True
                        time.sleep(0.01)
                        continue

                    last_packet_at = time.monotonic()
                    next_timeout_warning = last_packet_at + 5.0

                    # Bei stdout ('-') kann nicht nachträglich entschlüsselt werden;
                    # bei Dateiausgabe schreiben wir zunächst die schnellen Rohblöcke.
                    chunk_to_write = (
                        descramble_ts_block(ts_data[:complete_len])
                        if (decrypt_after and output_path == "-")
                        else ts_data[:complete_len]
                    )
                    out.write(chunk_to_write)
                    out.flush()
                    block_num += 1
                    ts_bytes += complete_len
                    retry_last = False

                    if block_num % 50 == 0:
                        elapsed = time.monotonic() - t_start
                        kbps = (ts_bytes / 1024) / max(elapsed, 0.001)
                        log.info(
                            "Block %4d | %.1f MiB | %.0f KB/s",
                            block_num, ts_bytes / 1_048_576, kbps,
                        )

            except KeyboardInterrupt:
                print()
                log.info("Abgebrochen.")
            finally:
                log.info(
                    "Stream beendet. %d Blöcke, %d Pulls, %.2f MiB",
                    block_num, pull_count, ts_bytes / 1_048_576,
                )

    finally:
        reset_prepared_prog_idx()
        if not tcp_sock_dead.is_set():
            try:
                with lock:
                    protocol.send_recv(
                        tcp_sock, protocol.cmd_stream_release(), 0, "0xF8/0x07 release"
                    )
            except OSError:
                pass
        stop.set()
        if ka is not None:
            ka.join(timeout=4.0)
        udp.close()

    if decrypt_after and output_path != "-" and ts_bytes > 0:
        decrypt_ts_file(output_path)


__all__ = [
    "DEFAULT_TS_KEY",
    "SIGNAL_INTVL",
    "UDP_BLOCK_SIZE",
    "UDP_PULL_INTVL",
    "decrypt_ts_file",
    "descramble_ts_block",
    "prepare_channel",
    "stream",
]
