"""
start_ui.py – Einfacher Starter für das WISI OR S2D Web Control Center
"""
import os
import sys
from pathlib import Path

# src Verzeichnis zum Python-Suchpfad hinzufügen
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from ui.app import run_ui

if __name__ == "__main__":
    run_ui(host="0.0.0.0", port=8888, open_browser=True)
