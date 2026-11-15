"""Kompatibilitätseinstieg – leitet an tools.menu und wisi.client weiter."""
from __future__ import annotations

import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent.parent)
_pkg = str(Path(__file__).resolve().parent)
sys.path = [p for p in sys.path if Path(p).resolve() != Path(_pkg).resolve()]
if _src not in sys.path:
    sys.path.insert(0, _src)

from tools.menu import main_menu  # noqa: E402


def main() -> None:
    """Leitet alte Aufrufe an den aktuellen Client weiter."""
    from wisi.client import main as current_main

    current_main()


__all__ = ["main", "main_menu"]


if __name__ == "__main__":
    main()
