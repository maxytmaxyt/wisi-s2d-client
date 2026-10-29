"""Analysiert APIX-Befehle und den F9/0A-Speedtest-Verkehr in klassischen PCAPs."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from protocol import UDP_PORT
from pcap_parser import analyze, packets


def run(path: str, extract_service_db: str | None = None) -> int:
    capture_path = Path(path)
    result = analyze(capture_path)
    if extract_service_db is not None:
        candidates = [
            pkt.payload
            for pkt in packets(capture_path)
            if (
                pkt.protocol == 17
                and pkt.source_port == UDP_PORT
                and pkt.payload.startswith(b"\xf9\x0a")
            )
        ]
        if not candidates:
            raise ValueError("In der PCAP-Datei wurde keine 0xF9/0x0A-Geräteantwort gefunden.")
        blob = max(candidates, key=len)
        Path(extract_service_db).write_bytes(blob)
        print(
            f"Größte 0xF9/0x0A-Geräteantwort ({len(blob)} Byte) "
            f"nach {extract_service_db} geschrieben."
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def run_service_db(_path: str) -> int:
    raise ValueError(
        "0xF9/0x0A is used for a speedtest by the analyzed APK, not as a channel database. "
        "Channel lists are available via TCP 0xF6/0x20 and 0xF6/0x21."
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pcap", nargs="?", help="Pfad zur klassischen PCAP-Datei")
    parser.add_argument(
        "--decode-service-db",
        metavar="DATEI",
        help="Legacy option; rejected because 0xF9/0x0A is a speedtest, not a channel database",
    )
    parser.add_argument(
        "--extract-service-db",
        help="Legacy option name; save the largest 0xF9/0x0A device reply unchanged",
    )
    args = parser.parse_args(argv)
    if bool(args.pcap) == bool(args.decode_service_db):
        parser.error("Genau eine PCAP-Datei oder --decode-service-db DATEI angeben.")
    try:
        if args.decode_service_db:
            if args.extract_service_db:
                parser.error("--extract-service-db kann nur mit einer PCAP-Datei verwendet werden.")
            return run_service_db(args.decode_service_db)
        return run(args.pcap, args.extract_service_db)
    except (OSError, ValueError) as exc:
        logging.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
