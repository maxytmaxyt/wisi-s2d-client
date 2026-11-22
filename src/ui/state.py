"""
state.py – Gemeinsamer Zustand und Instanzen für das Web Control Center
"""
from __future__ import annotations

from pathlib import Path

from ui.streamer import DongleManager

manager = DongleManager()

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
INDEX_HTML_PATH = STATIC_DIR / "index.html"
