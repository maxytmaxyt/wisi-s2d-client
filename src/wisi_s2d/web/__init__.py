"""Web package for WISI OR S2D DVB-over-IP Client."""

from .app import app, run_ui
from .streamer import DongleManager

__all__ = ["DongleManager", "app", "run_ui"]
