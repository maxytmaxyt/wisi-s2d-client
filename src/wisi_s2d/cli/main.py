"""Einfaches Überskript für die WISI-Dongle-Werkzeuge."""
from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path

# Allow `python src/wisi/wisi.py` (and all lazy `from wisi.*` imports
# inside main()) to work without installing the package first.
# This must happen before any wisi.* import is attempted.
_src = str(Path(__file__).resolve().parents[2])
_pkg = str(Path(__file__).resolve().parent)
# Remove the package directory from sys.path so 'wisi' resolves as a
# package rooted at src/, not as the script's own directory.
sys.path = [p for p in sys.path if Path(p).resolve() != Path(_pkg).resolve()]
if _src not in sys.path:
    sys.path.insert(0, _src)
if not __package__:
    __package__ = "wisi_s2d.cli"

# DEFAULT_IP is re-exported here from protocol so callers don't need to
# import protocol directly; we read it lazily to avoid a circular-import
# issue when running this file directly.
DEFAULT_IP: str = "192.168.178.32"  # mirrors protocol.DEFAULT_IP

log = logging.getLogger("wisi")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="WISI OR S2D: Senderliste, EPG, Stream, Discovery und PCAP-Werkzeuge."
    )
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP-Adresse des Dongles")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--ui", "--web", dest="ui", action="store_true", help="Web-Benutzeroberfläche starten")
    actions.add_argument("--channels", action="store_true", help="Senderliste anzeigen")
    actions.add_argument("--epg", action="store_true", help="EPG aller Sender als JSON laden")
    actions.add_argument("--stream", action="store_true", help="MPEG-TS-Stream starten")
    actions.add_argument(
        "--decrypt-ts",
        metavar="DATEI",
        help="Gespeicherte .ts-Datei entschlüsseln (z. B. stream.ts)",
    )
    actions.add_argument("--discover", action="store_true", help="Experimentelle UDP-Gerätesuche")
    actions.add_argument(
        "--probe-opcode",
        type=lambda value: int(value, 0),
        metavar="OPCODE",
        help="Einen einzelnen unbekannten Opcode testen, z. B. 0x12",
    )
    actions.add_argument("--pcap", metavar="DATEI", help="PCAP-Datei analysieren")
    actions.add_argument(
        "--decode-service-db",
        metavar="DATEI",
        help="Legacy option; rejected because 0xF9/0x0A is a speedtest, not a channel database",
    )
    parser.add_argument("--output", default="stream.ts", help="Stream-Datei oder - für stdout")
    parser.add_argument("--duration", type=float, default=0.0, help="Streamdauer in Sekunden")
    parser.add_argument(
        "--decrypt",
        action="store_true",
        help="Bei --stream: gespeicherte .ts-Datei am Ende automatisch entschlüsseln",
    )
    parser.add_argument("--pat-idx", type=int, default=4,
                        help="Interner Kanal-Index des Dongles (0–65535) für --stream")
    parser.add_argument("--epg-output", default="epg.json", help="EPG-Datei oder - für stdout")
    parser.add_argument(
        "--epg-limit", "--limit", dest="epg_limit", type=int,
        help="EPG nur für die ersten N Sender laden",
    )
    parser.add_argument(
        "--pcap-extract",
        help="Größte 0xF9/0x0A-Speedtest-Geräteantwort aus PCAP extrahieren",
    )
    parser.add_argument("--debug", action="store_true", help="Debug-Logs aktivieren")
    args = parser.parse_args(argv)

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    if args.duration < 0:
        parser.error("--duration darf nicht negativ sein.")
    if args.pat_idx < 0 or args.pat_idx > 65535:
        parser.error("--pat-idx muss zwischen 0 und 65535 liegen.")

    try:
        if args.ui:
            from ..web.app import run_ui

            run_ui(dongle_ip=args.ip)
            return 0
        if args.channels:
            from .channels import run as run_channels

            return run_channels(args.ip)
        if args.epg:
            from .epg import run as run_epg

            epg_out = (
                args.output
                if args.epg_output == "epg.json" and args.output != "stream.ts"
                else args.epg_output
            )
            return run_epg(args.ip, epg_out, args.epg_limit)
        if args.decrypt_ts:
            from .decrypt import run as decrypt_run

            out_target = args.output if args.output != "stream.ts" else None
            return decrypt_run(args.decrypt_ts, out_target)
        if args.stream:
            from .client import main as client_main

            forwarded = ["--ip", args.ip, "--stream", "--pat-idx", str(args.pat_idx),
                         "--output", args.output, "--duration", str(args.duration)]
            if args.decrypt:
                forwarded.append("--decrypt")
            if args.debug:
                forwarded.append("--debug")
            original_argv = sys.argv
            try:
                sys.argv = [sys.argv[0], *forwarded]
                client_main()
            finally:
                sys.argv = original_argv
            return 0
        if args.discover:
            from .discovery import run as run_discovery

            return run_discovery(args.ip, 2.0)
        if args.probe_opcode is not None:
            from .probe import run as run_probe

            return run_probe(args.ip, args.probe_opcode)
        if args.pcap:
            from .pcap import run as run_pcap

            return run_pcap(args.pcap, args.pcap_extract)
        if args.decode_service_db:
            from .pcap import run_service_db

            if args.pcap_extract:
                parser.error("--pcap-extract kann nicht mit --decode-service-db verwendet werden.")
            return run_service_db(args.decode_service_db)
        if args.pcap_extract:
            parser.error("--pcap-extract benötigt --pcap DATEI.")
        parser.print_help()
        return 0
    except (ConnectionError, OSError, ValueError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
