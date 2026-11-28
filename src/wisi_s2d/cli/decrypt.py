"""Gespeicherte MPEG-TS-Streamdateien (.ts) des WISI OR S2D Dongles entschlüsseln."""
from __future__ import annotations

import argparse
import logging
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

from ..core.decrypt import DEFAULT_TS_KEY, decrypt_ts_file, descramble_ts_block  # noqa: E402

log = logging.getLogger("wisi.decrypt")


def run(input_path: str, output_path: str | None = None) -> int:
    dst = decrypt_ts_file(input_path, output_path)
    print(f"TS-Datei entschlüsselt: {dst}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="Pfad zur verschlüsselten .ts-Datei (z. B. stream.ts)")
    parser.add_argument(
        "--output", "-o",
        help="Optionale Zieldatei (Standard: überschreibt die Eingabedatei in-place)",
    )
    args = parser.parse_args(argv)
    try:
        return run(args.input, args.output)
    except (FileNotFoundError, OSError, ValueError) as exc:
        log.error("%s", exc)
        return 1


__all__ = [
    "DEFAULT_TS_KEY",
    "decrypt_ts_file",
    "descramble_ts_block",
    "main",
    "run",
]


if __name__ == "__main__":
    sys.exit(main())
