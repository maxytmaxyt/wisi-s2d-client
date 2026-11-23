"""Experimenteller TV2S-UDP-Broadcast zur Gerätesuche."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import socket
import struct
import sys
import time
from collections.abc import Sequence
from pathlib import Path

# Allow running this file directly (python src/wisi/<file>.py):
_src = str(Path(__file__).resolve().parents[2])
_pkg = str(Path(__file__).resolve().parent)
# Remove the package directory from sys.path so 'wisi' resolves as a
# package rooted at src/, not as the script's own directory.
sys.path = [p for p in sys.path if Path(p).resolve() != Path(_pkg).resolve()]
if _src not in sys.path:
    sys.path.insert(0, _src)

from ..protocol import protocol
from ..protocol.protocol import TCP_PORT
from .common import DEFAULT_IP

log = logging.getLogger("wisi.discovery")

MAGIC = 0x54563253
VERSION = 0x0100
DISCOVERY_REQUEST = 0x0001
APP_ID = "com.tivicon.tv2smart"


def probe_dongle_tcp(ip: str, timeout: float = 0.25) -> dict[str, object] | None:
    """Prüft eine IP auf TCP Port 8802 und verifiziert das APIX 0xF6/0x16 Handshake."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, TCP_PORT))
        s.sendall(protocol.cmd_16())
        resp = s.recv(25)
        s.close()
        if len(resp) >= 3 and resp[:2] == b"\xf6\x16":
            return {
                "ip": ip,
                "model_name": "WISI OR S2D",
                "port": TCP_PORT,
                "status": resp[2],
            }
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    return None


def discover_dongles(current_ip: str | None = None, timeout: float = 1.5) -> list[dict[str, object]]:
    """
    Sucht den WISI Dongle zuverlässig und bestätigt über TCP Port 8802 (APIX 0xF6/0x16).
    1. Sofortige Prüfung der aktuellen und bekannten Standard-IPs (Dauer: ~100 ms).
    2. Paralleler Subnetz-Scan lokaler Schnittstellen (Dauer: < 1 s).
    """
    prio_ips = [current_ip, DEFAULT_IP, "10.20.0.1", "192.168.2.80", "192.168.1.32", "192.168.0.32"]
    checked: set[str] = set()
    found: list[dict[str, object]] = []

    for ip in prio_ips:
        if ip and ip not in checked:
            checked.add(ip)
            res = probe_dongle_tcp(ip, timeout=0.3)
            if res:
                found.append(res)

    if found:
        return found

    candidates: list[str] = []
    try:
        host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        host_ips = []

    subnets: set[str] = {"192.168.178"}
    for hip in host_ips:
        if not (hip.startswith("127.") or hip.startswith("169.254.")):
            parts = hip.split(".")
            if len(parts) == 4:
                subnets.add(".".join(parts[:3]))

    for subnet in subnets:
        for i in range(1, 255):
            candidate = f"{subnet}.{i}"
            if candidate not in checked:
                candidates.append(candidate)

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        futures = {executor.submit(probe_dongle_tcp, ip, 0.25): ip for ip in candidates}
        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                if res and res not in found:
                    found.append(res)
            except Exception:
                pass

    return found


def build_request(sequence_id: int) -> bytes:
    payload = json.dumps(
        {"cmd": "DISCOVER_DONGLE", "app_id": APP_ID},
        separators=(",", ":"),
    ).encode("ascii")
    header = struct.pack(">IHHII", MAGIC, VERSION, DISCOVERY_REQUEST, sequence_id, len(payload))
    return header + payload


def parse_response(data: bytes) -> dict[str, object] | None:
    if len(data) < 16:
        return None
    magic, _version, _opcode, _sequence_id, payload_length = struct.unpack_from(">IHHII", data)
    if magic != MAGIC or payload_length != len(data) - 16:
        return None
    try:
        result = json.loads(data[16:].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(result, dict):
        return None
    return result


def run(ip: str, timeout: float = 2.0) -> int:
    devices = discover_dongles(current_ip=ip, timeout=timeout)
    if devices:
        for dev in devices:
            print(json.dumps(dev, ensure_ascii=False, indent=2))
        return 0
    log.warning("Kein WISI Dongle gefunden (geprüft auf Port %d).", TCP_PORT)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default=DEFAULT_IP, help="Zusätzliche Ziel-IP")
    parser.add_argument("--timeout", type=float, default=2.0, help="Wartezeit in Sekunden")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout muss größer als 0 sein.")
    try:
        return run(args.ip, args.timeout)
    except OSError as exc:
        log.error("Discovery fehlgeschlagen: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
