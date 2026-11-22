"""
WISI / Tivizen / TiViCon DVB-over-IP Client – v4 (PCAP-verified)
================================================================
Archivierte Referenzimplementierung des PCAP-Mitschnitts.
TCP 8802 (Steuerkanal 0xF6), UDP 8800 (Stream 0xF9).
"""

import argparse
import logging
import socket
import struct
import sys
import threading
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wisi")

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
from wisi_proto_legacy import (
    DONGLE_IP,
    KA_SECS,
    PRE_SECS,
    STREAM_MS,
    TCP_PORT,
    TS_SYNC,
    UDP_PORT,
    tcp_16,
    tcp_17,
    tcp_epg_data,
    tcp_epg_size,
    tcp_evt_data,
    tcp_evt_size,
    udp_01,
    udp_02,
    udp_0a,
)

# ---------------------------------------------------------------------------
# TCP-Helfer
# ---------------------------------------------------------------------------

def _drain(sock: socket.socket, n: int = 0, timeout: float = 1.5) -> bytes:
    total = n + 13
    sock.settimeout(timeout)
    buf = bytearray()
    try:
        while len(buf) < total:
            chunk = sock.recv(min(4096, total - len(buf)))
            if not chunk:
                break
            buf.extend(chunk)
    except socket.timeout:
        pass
    finally:
        sock.settimeout(None)
    return bytes(buf)


def tcp_cmd(sock: socket.socket, lock: threading.Lock, cmd: bytes,
            exp: int = 0, label: str = "") -> bytes:
    with lock:
        sock.sendall(cmd)
        resp = _drain(sock, exp)
    if label:
        log.debug("TCP %-18s → %d Byte", label, len(resp))
    return resp

# ---------------------------------------------------------------------------
# Keep-Alive  (TCP 0x16 alle KA_SECS Sekunden)
# ---------------------------------------------------------------------------

def _keepalive(sock: socket.socket, lock: threading.Lock,
               stop: threading.Event) -> None:
    cmd = tcp_16()
    while not stop.wait(KA_SECS):
        try:
            tcp_cmd(sock, lock, cmd, exp=12, label="0x16 (KA)")
        except OSError as e:
            log.debug("Keep-Alive-Fehler: %s", e)
            break
    log.debug("Keep-Alive-Thread beendet.")

# ---------------------------------------------------------------------------
# Init + EPG (TCP)
# ---------------------------------------------------------------------------

def init(sock: socket.socket, lock: threading.Lock) -> None:
    log.info("Init: APIX 0x16 ...")
    tcp_cmd(sock, lock, tcp_16(), exp=12, label="0x16")
    log.info("Init: APIX 0x17 ...")
    tcp_cmd(sock, lock, tcp_17(), exp=4,  label="0x17")
    log.info("Init abgeschlossen.")


def fetch_epg(sock: socket.socket, lock: threading.Lock,
              idx: int) -> bytes | None:
    log.info("EPG 0x%08X ...", idx)
    r = tcp_cmd(sock, lock, tcp_epg_size(idx), exp=6, label="0x30")
    if len(r) < 6:
        return None
    off  = 2 if r[:2] == b"\xF6\x30" else 0
    size = struct.unpack(">I", r[off:off+4])[0]
    r2   = tcp_cmd(sock, lock, tcp_epg_data(idx, size), exp=size, label="0x31")
    return r2[2:] if r2[:2] == b"\xF6\x31" else r2

# ---------------------------------------------------------------------------
# UDP-Stream  (gesamte Stream-Logik läuft auf UDP Port 8800)
# ---------------------------------------------------------------------------

def udp_stream(dongle_ip: str, output: Path,
               pre_secs: float, stop: threading.Event) -> None:

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 * 1024 * 1024)
    udp.bind(("0.0.0.0", UDP_PORT))
    udp.settimeout(1.0)
    dst = (dongle_ip, UDP_PORT)

    # ── Phase 1: 0x02 ──────────────────────────────────────────────────────
    log.info("UDP Pre-Stream: APIX 0x02 ...")
    udp.sendto(udp_02(), dst)
    try:
        d, _ = udp.recvfrom(65535)
        log.debug("0x02 Antwort: %d Byte", len(d))
    except socket.timeout:
        log.debug("0x02: keine Antwort (OK)")

    # ── Phase 2: 0x0A Schleife ─────────────────────────────────────────────
    log.info("UDP Pre-Stream: APIX 0x0A Schleife für %.1f s ...", pre_secs)
    cmd_0a   = udp_0a()
    t_end    = time.monotonic() + pre_secs
    loop_n   = 0
    while time.monotonic() < t_end and not stop.is_set():
        udp.sendto(cmd_0a, dst)
        try:
            d, _ = udp.recvfrom(65535)
            log.debug("0x0A #%d → %d Byte", loop_n, len(d))
        except socket.timeout:
            pass
        loop_n += 1
        time.sleep(0.05)
    log.info("0x0A Schleife abgeschlossen (%d Iterationen).", loop_n)

    # ── Phase 3: 0x01 Dauerschleife ────────────────────────────────────────
    log.info("UDP Live-Stream: APIX 0x01. STRG+C zum Beenden.")
    cmd_01  = udp_01()
    n_pkts  = 0
    n_bytes = 0

    with output.open("wb") as fh:
        while not stop.is_set():
            udp.sendto(cmd_01, dst)

            # Alle Antworten innerhalb STREAM_MS lesen
            deadline = time.monotonic() + STREAM_MS
            while time.monotonic() < deadline and not stop.is_set():
                try:
                    data, _ = udp.recvfrom(65535)
                except socket.timeout:
                    break

                # USBS-Status oder 0x0A-Nullpaket → überspringen
                if data[:4] == b"USBS" or data[:2] == b"\xf9\x0a":
                    continue

                # TS-Sync suchen
                if data[0] == TS_SYNC:
                    ts = data
                elif TS_SYNC in data[:200]:
                    ts = data[data.index(TS_SYNC):]
                else:
                    log.debug("Kein TS-Sync (%d Byte verworfen)", len(data))
                    continue

                fh.write(ts)
                fh.flush()
                n_pkts  += 1
                n_bytes += len(ts)
                sys.stdout.write(
                    f"\r  UDP-Blöcke: {n_pkts:5d}  |  "
                    f"TS-Daten: {n_bytes / 1_048_576:.2f} MiB"
                )
                sys.stdout.flush()

    udp.close()
    print()
    log.info("UDP gestoppt. %d Blöcke, %.2f MiB.", n_pkts, n_bytes / 1_048_576)

# ---------------------------------------------------------------------------
# Haupt-Controller
# ---------------------------------------------------------------------------

def run(ip: str, output: Path, epg_idx: int | None, pre_secs: float) -> None:
    stop = threading.Event()
    lock = threading.Lock()

    log.info("Verbinde TCP %s:%d ...", ip, TCP_PORT)
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.settimeout(10.0)
    try:
        tcp.connect((ip, TCP_PORT))
    except OSError as e:
        log.error("TCP-Verbindung fehlgeschlagen: %s", e)
        return
    tcp.settimeout(None)
    log.info("TCP-Steuerkanal verbunden.")

    try:
        init(tcp, lock)

        threading.Thread(target=_keepalive, args=(tcp, lock, stop),
                         daemon=True, name="tcp-ka").start()

        if epg_idx is not None:
            xml = fetch_epg(tcp, lock, epg_idx)
            if xml:
                f = output.with_suffix(".epg.xml")
                f.write_bytes(xml)
                log.info("EPG → %s", f)

        udp_stream(ip, output, pre_secs, stop)

    except KeyboardInterrupt:
        log.info("Streaming durch Nutzer beendet.")
    except OSError as e:
        log.error("Fehler: %s", e)
    finally:
        stop.set()
        try:
            tcp.close()
        except Exception:
            pass
        log.info("Verbindung geschlossen. Stream-Datei: %s", output)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(
        description="WISI / Tivizen DVB-over-IP Client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--ip",         default=DONGLE_IP, help="IP des Dongles")
    p.add_argument("--output",     default="live_tv_stream.ts",
                   help="Ausgabe-TS-Datei")
    p.add_argument("--epg-idx",    type=lambda x: int(x, 0), default=None,
                   help="EPG-Programm-Index (hex/dez), z.B. 0x40B7008F")
    p.add_argument("--pre-stream", type=float, default=PRE_SECS,
                   help="Dauer der 0x0A-Vorbereitungsschleife in Sekunden")
    p.add_argument("--debug",      action="store_true", help="Debug-Logging")
    args = p.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    run(ip=args.ip, output=Path(args.output),
        epg_idx=args.epg_idx, pre_secs=args.pre_stream)


if __name__ == "__main__":
    main()
