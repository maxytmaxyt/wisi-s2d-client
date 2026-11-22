"""
WISI / Tivizen / TiViCon DVB-over-IP Client (v1 Archiv)
=======================================================
Archivierte Originalimplementierung des Reverse-Engineering-Prozesses.
TCP 8802 (Steuerkanal), UDP 8800 (Datenpfad).
"""

import argparse
import logging
import select
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
# Standard-Konfiguration
# ---------------------------------------------------------------------------
DONGLE_IP   = "192.168.178.32"
TCP_PORT    = 8802
UDP_PORT    = 8800

from wisi_dongle_v1_cmds import (
    MAGIC_TAG,
    TS_PACKET_SIZE,
    TS_PACKETS_PER_BLOCK,
    TS_SYNC_BYTE,
    UDP_PAYLOAD_EXPECTED,
    cmd_epg_data,
    cmd_epg_size,
    cmd_event_data,
    cmd_event_size,
    cmd_init_16,
    cmd_init_17,
    cmd_pre_stream_02,
    cmd_pre_stream_0a,
    cmd_stream_01,
    drain,
    recv_exact,
    send_cmd,
)





# ---------------------------------------------------------------------------
# Initialisierungssequenz
# ---------------------------------------------------------------------------

def handshake(sock: socket.socket) -> None:
    log.info("Init: APIX 0x16 ...")
    send_cmd(sock, cmd_init_16(), expected_data=12, label="APIX 0x16")

    log.info("Init: APIX 0x17 ...")
    send_cmd(sock, cmd_init_17(), expected_data=4,  label="APIX 0x17")

    log.info("Init abgeschlossen.")


# ---------------------------------------------------------------------------
# EPG-Abfrage (optional)
# ---------------------------------------------------------------------------

def fetch_epg(sock: socket.socket, prog_idx: int) -> bytes | None:
    log.info("EPG-Größe für prog_idx=0x%08X ...", prog_idx)
    resp = send_cmd(sock, cmd_epg_size(prog_idx), expected_data=6, label="APIX 0x30")
    if len(resp) < 6:
        log.error("Zu kurze Größenantwort (%d Byte)", len(resp))
        return None

    # Antwort: F6 30 xx xx xx xx  (4 Byte Länge Big-Endian)
    offset = 2 if resp[:2] == b"\xF6\x30" else 0
    epg_size = struct.unpack(">I", resp[offset:offset + 4])[0]
    log.info("EPG-Datensatz: %d Byte", epg_size)

    resp2 = send_cmd(sock, cmd_epg_data(prog_idx, epg_size),
                     expected_data=epg_size, label="APIX 0x31")
    xml = resp2[2:] if resp2[:2] == b"\xF6\x31" else resp2
    log.info("EPG-XML: %d Byte empfangen", len(xml))
    return xml


# ---------------------------------------------------------------------------
# UDP-Empfänger-Thread
# ---------------------------------------------------------------------------

def _udp_receiver_worker(output_path: Path, stop_event: threading.Event,
                          udp_port: int = UDP_PORT) -> None:
    log.info("UDP-Empfänger auf Port %d → %s", udp_port, output_path)
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
    udp_sock.bind(("0.0.0.0", udp_port))
    udp_sock.settimeout(3.0)

    packet_count = 0
    byte_count   = 0

    with output_path.open("wb") as fh:
        while not stop_event.is_set():
            try:
                data, _addr = udp_sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError as exc:
                log.error("UDP-Fehler: %s", exc)
                break

            # Sync-Byte 0x47 suchen (TiViCon-Header überspringen)
            start = data.find(TS_SYNC_BYTE.to_bytes(1, "big"))
            if start == -1:
                log.debug("Kein TS-Sync, Block verworfen (%d Byte)", len(data))
                continue

            ts_payload = data[start:]
            fh.write(ts_payload)
            fh.flush()

            packet_count += 1
            byte_count   += len(ts_payload)
            sys.stdout.write(
                f"\r  UDP-Blöcke: {packet_count:5d}  |  "
                f"TS-Daten: {byte_count / 1_048_576:.1f} MiB"
            )
            sys.stdout.flush()

    udp_sock.close()
    print()
    log.info("UDP gestoppt. %d Blöcke, %.1f MiB", packet_count, byte_count / 1_048_576)


# ---------------------------------------------------------------------------
# Haupt-Controller
# ---------------------------------------------------------------------------

def run_controller(ip: str, output: Path, epg_prog_idx: int | None,
                   pre_stream_secs: float) -> None:
    """
    Vollständiger Ablauf:
      1. TCP + Handshake (0x16 / 0x17)
      2. Opt. EPG-Abfrage
      3. APIX 0x02 (einmalig)
      4. APIX 0x0A in Schleife für ~pre_stream_secs Sekunden
      5. UDP-Empfänger starten
      6. APIX 0x01 in Dauerschleife → UDP liefert MPEG-TS
    """
    log.info("Verbinde mit %s:%d ...", ip, TCP_PORT)
    stop_event = threading.Event()

    tcp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_sock.settimeout(10.0)
    try:
        tcp_sock.connect((ip, TCP_PORT))
    except OSError as exc:
        log.error("TCP-Verbindung fehlgeschlagen: %s", exc)
        return
    tcp_sock.settimeout(None)
    log.info("TCP-Steuerkanal verbunden.")

    try:
        # 1. Initialisierung
        handshake(tcp_sock)

        # 2. Optionale EPG-Abfrage
        if epg_prog_idx is not None:
            xml = fetch_epg(tcp_sock, epg_prog_idx)
            if xml:
                epg_file = output.with_suffix(".epg.xml")
                epg_file.write_bytes(xml)
                log.info("EPG gespeichert: %s", epg_file)

        # 3. APIX 0x02 (Einmalig, laut PCAP vor der 0x0A-Schleife)
        log.info("Pre-Stream: APIX 0x02 ...")
        send_cmd(tcp_sock, cmd_pre_stream_02(), expected_data=0, label="APIX 0x02")

        # 4. APIX 0x0A – Schleife (~entspricht dem PCAP-Zeitfenster 4,98–30,41 s)
        log.info("Pre-Stream: APIX 0x0A Schleife für %.1f s ...", pre_stream_secs)
        t_end = time.monotonic() + pre_stream_secs
        loop_count = 0
        while time.monotonic() < t_end:
            send_cmd(tcp_sock, cmd_pre_stream_0a(),
                     expected_data=0, label=f"APIX 0x0A #{loop_count}")
            loop_count += 1
            time.sleep(PRE_STREAM_INTERVAL)
        log.info("0x0A Schleife abgeschlossen (%d Iterationen).", loop_count)

        # 5. UDP-Empfänger starten (bevor 0x01 getriggert wird)
        udp_thread = threading.Thread(
            target=_udp_receiver_worker,
            args=(output, stop_event),
            daemon=True,
            name="udp-recv",
        )
        udp_thread.start()
        time.sleep(0.2)

        # 6. APIX 0x01 – Dauerschleife, löst UDP-Datagramme aus
        log.info("Live-Stream aktiv (APIX 0x01). STRG+C zum Beenden.")
        stream_cmd = cmd_stream_01()
        while True:
            # Senden + USBS sofort lesen (verhindert Buffer-Overflow → Reset)
            send_cmd(tcp_sock, stream_cmd, expected_data=0, label="APIX 0x01")
            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Streaming durch Nutzer beendet.")
    except OSError as exc:
        log.error("Netzwerkfehler: %s", exc)
    finally:
        stop_event.set()
        try:
            tcp_sock.close()
        except Exception:
            pass
        log.info("Verbindung geschlossen. Stream-Datei: %s", output)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="WISI / Tivizen DVB-over-IP Client",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--ip",          default=DONGLE_IP,
                   help="IP-Adresse des Dongles")
    p.add_argument("--output",      default="live_tv_stream.ts",
                   help="Ausgabedatei für den MPEG-TS-Stream")
    p.add_argument("--epg-idx",     type=lambda x: int(x, 0), default=None,
                   help="Programm-Index für EPG-Abfrage (hex/dez), z.B. 0x40B7008F")
    p.add_argument("--pre-stream",  type=float, default=PRE_STREAM_LOOP_SECS,
                   help="Sekunden für die APIX-0x0A-Vorbereitungsschleife")
    p.add_argument("--debug",       action="store_true",
                   help="Debug-Logging aktivieren")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    run_controller(
        ip              = args.ip,
        output          = Path(args.output),
        epg_prog_idx    = args.epg_idx,
        pre_stream_secs = args.pre_stream,
    )


if __name__ == "__main__":
    main()
