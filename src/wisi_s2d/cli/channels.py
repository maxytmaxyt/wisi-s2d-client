"""Load and display the dongle channel list fetched over TCP."""
from __future__ import annotations

import argparse
import logging
import sys
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
if not __package__:
    __package__ = "wisi_s2d.cli"

from .common import DEFAULT_IP, load_services

log = logging.getLogger("wisi.channels")


def run(ip: str) -> int:
    services = load_services(ip)
    print(f"{'Index':>5} {'SID':>6} {'prog_idx':>10} {'vPID':>6} {'aPID':>6} {'Status':>8}  Name")
    for service in services:
        state = "verschl." if service.is_encrypted else "FTA"
        print(
            f"{service.pat_index:>4} {service.service_id:>6} "
            f"0x{service.prog_idx:08X} 0x{service.video_pid:04X} "
            f"0x{service.audio_pid:04X} {state:>8}  {service.name}"
        )
    print(f"\n{len(services)} Sender gefunden.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", default=DEFAULT_IP, help="IP-Adresse des Dongles")
    args = parser.parse_args(argv)
    try:
        return run(args.ip)
    except (ConnectionError, OSError) as exc:
        log.error("%s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
