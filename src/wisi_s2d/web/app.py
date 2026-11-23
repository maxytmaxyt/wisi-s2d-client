"""
app.py – Starlette Web Application für das WISI OR S2D Control Center
====================================================================
Modularer Aufbau (< 300 Zeilen):
  - api_stream.py: Streaming, Kanäle, EPG, Status, Diagnose
  - api_record.py: Aufnahmen, Timer-Planer, Tuner & Suchlauf
  - state.py:      Gemeinsame Manager-Instanz und Pfade
  - static/index.html: Web-Benutzeroberfläche (HTML5, CSS3, JS)
"""
from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
import webbrowser

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .api_record import (
    api_record_start,
    api_record_stop,
    api_recording_delete,
    api_recording_file,
    api_recording_stream,
    api_recordings_convert,
    api_recordings_decrypt,
    api_recordings_list,
    api_timers_create,
    api_timers_delete,
    api_timers_list,
    api_timeshift_save,
    api_tuner_scan_start,
    api_tuner_scan_stop,
    api_tuner_tune,
)
from .api_stream import (
    api_channels,
    api_channels_refresh,
    api_connect,
    api_disconnect,
    api_discover,
    api_epg,
    api_epg_refresh,
    api_info,
    api_pcap_analyze,
    api_playlist_m3u,
    api_probe,
    api_status,
    api_stream_stop,
    api_stream_video,
)
from .state import INDEX_HTML_PATH, STATIC_DIR, manager

log = logging.getLogger("wisi.ui.app")

# HTML-Vorlage laden
if INDEX_HTML_PATH.is_file():
    _HTML_PAGE = INDEX_HTML_PATH.read_text(encoding="utf-8")
else:
    _HTML_PAGE = "<h1>WISI Control Center</h1><p>index.html nicht gefunden.</p>"


async def index(request: Request) -> HTMLResponse:
    """Liefert die Benutzeroberfläche aus mit automatischem Cache-Busting."""
    raw = INDEX_HTML_PATH.read_text(encoding="utf-8") if INDEX_HTML_PATH.is_file() else _HTML_PAGE
    v_param = f"?v={int(time.time())}"
    raw = raw.replace(".js\"", f".js{v_param}\"").replace(".css\"", f".css{v_param}\"")
    return HTMLResponse(
        raw,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ---------------------------------------------------------------------------
# Starlette Routing
# ---------------------------------------------------------------------------
routes = [
    Route("/", endpoint=index, methods=["GET"]),
    Route("/playlist.m3u", endpoint=api_playlist_m3u, methods=["GET"]),
    Route("/api/status", endpoint=api_status, methods=["GET"]),
    Route("/api/connect", endpoint=api_connect, methods=["POST"]),
    Route("/api/disconnect", endpoint=api_disconnect, methods=["POST"]),
    Route("/api/discover", endpoint=api_discover, methods=["POST"]),
    Route("/api/info", endpoint=api_info, methods=["GET"]),
    Route("/api/channels", endpoint=api_channels, methods=["GET"]),
    Route("/api/channels/refresh", endpoint=api_channels_refresh, methods=["POST"]),
    Route("/api/epg", endpoint=api_epg, methods=["GET"]),
    Route("/api/epg/refresh", endpoint=api_epg_refresh, methods=["POST"]),
    Route("/api/stream/stop", endpoint=api_stream_stop, methods=["POST"]),
    Route("/api/stream/{prog_idx}", endpoint=api_stream_video, methods=["GET"]),
    Route("/api/record/start", endpoint=api_record_start, methods=["POST"]),
    Route("/api/record/stop", endpoint=api_record_stop, methods=["POST"]),
    Route("/api/timeshift/save", endpoint=api_timeshift_save, methods=["POST"]),
    Route("/api/recordings", endpoint=api_recordings_list, methods=["GET"]),
    Route("/api/recordings/stream/{filename:path}", endpoint=api_recording_stream, methods=["GET"]),
    Route("/api/recordings/convert", endpoint=api_recordings_convert, methods=["POST"]),
    Route("/api/recordings/{filename}", endpoint=api_recording_file, methods=["GET"]),
    Route("/api/recordings/{filename}", endpoint=api_recording_delete, methods=["DELETE"]),
    Route("/api/recordings/decrypt", endpoint=api_recordings_decrypt, methods=["POST"]),
    Route("/api/timers", endpoint=api_timers_list, methods=["GET"]),
    Route("/api/timers", endpoint=api_timers_create, methods=["POST"]),
    Route("/api/timers/{timer_id}", endpoint=api_timers_delete, methods=["DELETE"]),
    Route("/api/tuner/tune", endpoint=api_tuner_tune, methods=["POST"]),
    Route("/api/tuner/scan/start", endpoint=api_tuner_scan_start, methods=["POST"]),
    Route("/api/tuner/scan/stop", endpoint=api_tuner_scan_stop, methods=["POST"]),
    Route("/api/probe", endpoint=api_probe, methods=["POST"]),
    Route("/api/pcap/analyze", endpoint=api_pcap_analyze, methods=["POST"]),
    Mount("/static", app=StaticFiles(directory=str(STATIC_DIR)), name="static"),
]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = Starlette(routes=routes, middleware=middleware)


def run_ui(
    host: str = "0.0.0.0",
    port: int = 8888,
    dongle_ip: str | None = None,
    open_browser: bool = True,
) -> None:
    """Startet den Webserver und öffnet optional die Benutzeroberfläche im Browser."""
    import uvicorn

    if dongle_ip:
        manager.ip = dongle_ip

    display_host = "localhost" if host in ("0.0.0.0", "") else host
    url = f"http://{display_host}:{port}"
    print("\n" + "=" * 64)
    print("  WISI OR S2D – DVB-over-IP Web Control Center")
    print(f"  Lokale URL:        {url}")
    print(f"  Netzwerk-Bind:     http://{host}:{port}")
    print(f"  Dongle Standard-IP: {manager.ip}")
    print("=" * 64 + "\n")

    if open_browser:
        def _open():
            time.sleep(1.0)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_ui()
