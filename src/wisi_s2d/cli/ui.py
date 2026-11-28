"""Startet die Web-Benutzeroberfläche des WISI OR S2D Clients."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

_src = str(Path(__file__).resolve().parents[2])
_pkg = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if Path(p).resolve() != Path(_pkg).resolve()]
if _src not in sys.path:
    sys.path.insert(0, _src)
if not __package__:
    __package__ = "wisi_s2d.cli"

from ..protocol import protocol
from ..web.app import run_ui


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default=protocol.DEFAULT_IP, help="Standard-IP des Dongles")
    parser.add_argument("--host", default="0.0.0.0", help="Webserver Bind-Host (Standard: 0.0.0.0 für Heimnetzwerk)")
    parser.add_argument("--port", type=int, default=8888, help="Webserver Port (Standard: 8888)")
    parser.add_argument("--no-browser", action="store_true", help="Browser nicht automatisch öffnen")
    parser.add_argument(
        "--auto-connect",
        action="store_true",
        help="Beim Start automatisch nach dem Dongle suchen und verbinden",
    )
    args = parser.parse_args(argv)

    try:
        run_ui(
            host=args.host,
            port=args.port,
            dongle_ip=args.ip,
            open_browser=not args.no_browser,
            auto_connect=args.auto_connect,
        )
        return 0
    except (KeyboardInterrupt, SystemExit):
        return 0
    except Exception as exc:
        print(f"Fehler beim Starten der Benutzeroberfläche: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
