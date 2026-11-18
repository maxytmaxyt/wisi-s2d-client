"""
app.py – Starlette Web Application & REST API für den WISI OR S2D Client
========================================================================
Bietet eine moderne Web-Benutzeroberfläche und REST-Endpunkte für:
  - Live-TV & Radio Streaming (im Browser per mpegts.js & via VLC / M3U)
  - Senderliste & Filter (TV, Radio, FTA, Verschlüsselt)
  - Elektronischen Programmführer (EPG)
  - DVB-S2 Tuner & Sendersuchlauf (Transponder, LNB, DiSEqC)
  - Aufnahmen & TS-Dateientschlüsselung (AES-128-ECB)
  - Hardware-/Firmware-Informationen & Signalüberwachung (AGC, SNR)
  - PCAP- und Opcode-Diagnosewerkzeuge
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import html
import json
import logging
import os
from pathlib import Path
import queue
import time

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from decrypt import decrypt_ts_file
import protocol
from tools.pcap_parser import analyze as pcap_analyze
from ui.streamer import RECORDINGS_DIR, DongleManager
import wisi.discovery as discovery
import wisi.probe as probe_mod

log = logging.getLogger("wisi.ui.app")

manager = DongleManager()

STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------
async def api_status(request: Request) -> JSONResponse:
    """Liefert aktuellen Verbindungs-, Signal- und Streaming-Status."""
    active_ch = manager.active_service
    return JSONResponse({
        "connected": manager.is_connected(),
        "ip": manager.ip,
        "signal": {
            "locked": manager.signal_locked,
            "strength": manager.signal_strength,
            "quality": manager.signal_quality,
        },
        "streaming": manager.stream_stats,
        "recording": {
            "active": manager.recording_active,
            "path": str(manager.recording_path.name) if manager.recording_path else "",
            "bytes": manager.recording_bytes,
            "seconds": round(time.time() - manager.recording_start_time, 1) if manager.recording_active else 0,
        },
        "scan": manager.scan_status,
        "channels_count": len(manager.channels),
        "epg_count": len(manager.epg_data),
    })


async def api_connect(request: Request) -> JSONResponse:
    """Verbindet mit dem Dongle unter der angegebenen IP."""
    try:
        body = await request.json()
        ip = body.get("ip", manager.ip)
    except Exception:
        ip = manager.ip

    ok, msg = await asyncio.to_thread(manager.connect, ip)
    return JSONResponse({"success": ok, "message": msg, "ip": manager.ip})


async def api_disconnect(request: Request) -> JSONResponse:
    """Trennt die Verbindung zum Dongle."""
    await asyncio.to_thread(manager.disconnect)
    return JSONResponse({"success": True, "message": "Verbindung getrennt"})


async def api_discover(request: Request) -> JSONResponse:
    """Führt eine UDP-Gerätesuche im lokalen Netzwerk durch."""
    def _do_discover():
        import socket
        sequence_id = int(time.time()) & 0xFFFFFFFF
        req = discovery.build_request(sequence_id)
        found = []
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp.settimeout(1.5)
            try:
                udp.sendto(req, ("255.255.255.255", protocol.TCP_PORT))
                udp.sendto(req, (manager.ip, protocol.TCP_PORT))
            except Exception:
                pass
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                try:
                    data, addr = udp.recvfrom(65535)
                    parsed = discovery.parse_response(data)
                    if parsed:
                        found.append({"ip": addr[0], **parsed})
                except TimeoutError:
                    break
                except Exception:
                    pass
        return found

    results = await asyncio.to_thread(_do_discover)
    return JSONResponse({"success": True, "devices": results})


async def api_info(request: Request) -> JSONResponse:
    """Liefert Hardware-, Firmware- und Session-Informationen."""
    return JSONResponse({"success": True, "info": manager.dongle_info})


async def api_channels(request: Request) -> JSONResponse:
    """Gibt die Liste der Sender zurück (angereichert mit EPG-Daten)."""
    ch_list = []
    channels_source = manager.channels
    if not channels_source and manager.services:
        channels_source = [
            Channel(
                prog_idx=s.prog_idx,
                service_id=s.service_id,
                ts_id=1,
                freq=11362,
                pol="H",
                sym=22000,
                lcn=s.pat_index,
                name=s.name,
                fta=not s.is_encrypted,
                ch_type="RD" if s.is_radio else "TV",
            )
            for s in manager.services
        ]

    for ch in sorted(channels_source, key=lambda c: (c.lcn if c.lcn > 0 else 999999, c.name.lower())):
        events = manager.epg_data.get(ch.service_id, [])
        cur_event = events[0] if events else None
        next_event = events[1] if len(events) > 1 else None
        ch_list.append({
            "prog_idx": ch.prog_idx,
            "prog_idx_hex": f"0x{ch.prog_idx:08X}",
            "service_id": ch.service_id,
            "ts_id": ch.ts_id,
            "freq": ch.freq,
            "pol": ch.pol,
            "sym": ch.sym,
            "lcn": ch.lcn,
            "name": ch.name,
            "fta": ch.fta,
            "is_radio": ch.is_radio,
            "is_encrypted": ch.is_encrypted,
            "ch_type": ch.ch_type,
            "current_show": cur_event.get("title", "") if cur_event else "",
            "current_time": f"{cur_event.get('time', '')} ({cur_event.get('duration', '')})" if cur_event else "",
            "next_show": next_event.get("title", "") if next_event else "",
        })
    return JSONResponse({"success": True, "count": len(ch_list), "channels": ch_list})


async def api_channels_refresh(request: Request) -> JSONResponse:
    """Lädt die Kanalliste frisch vom Dongle über TCP 0xF6/0x20+0x21."""
    channels = await asyncio.to_thread(manager.refresh_channels)
    return JSONResponse({"success": True, "count": len(channels), "message": f"{len(channels)} Kanäle geladen"})


async def api_epg(request: Request) -> JSONResponse:
    """Liefert die EPG-Einträge gruppiert nach Service-ID."""
    return JSONResponse({"success": True, "epg": manager.epg_data})


async def api_epg_refresh(request: Request) -> JSONResponse:
    """Fragt EPG-Daten vom Dongle ab."""
    try:
        body = await request.json()
        limit = body.get("limit")
    except Exception:
        limit = 30
    epg = await asyncio.to_thread(manager.refresh_epg, limit)
    return JSONResponse({"success": True, "count": len(epg), "message": f"EPG für {len(epg)} Sender geladen"})


# ---------------------------------------------------------------------------
# Live Streaming & Playback
# ---------------------------------------------------------------------------
async def api_stream_video(request: Request) -> Response:
    """
    HTTP Live MPEG-TS Stream:
    Entschlüsselt TS-Pakete in Echtzeit und streamt sie chunked an den Browser oder VLC.
    """
    prog_idx_str = request.path_params.get("prog_idx")
    try:
        prog_idx = int(prog_idx_str, 0)
    except (ValueError, TypeError):
        return Response("Ungültiger prog_idx", status_code=400)

    # Stream im Manager starten falls noch nicht aktiv
    if not (manager.active_service and manager.active_service.prog_idx == prog_idx and manager.stream_thread and manager.stream_thread.is_alive()):
        ok = await asyncio.to_thread(manager.start_stream, prog_idx)
        if not ok:
            return Response("Konnte Stream nicht starten (Dongle nicht erreichbar)", status_code=502)

    # Client-Warteschlange abonnieren
    client_q = manager.subscribe_client()

    async def stream_generator() -> AsyncIterator[bytes]:
        try:
            while True:
                # Prüfe auf Client-Disconnect
                if await request.is_disconnected():
                    break
                try:
                    # Nicht-blockierend mit kurzem Timeout abfragen
                    chunk = await asyncio.to_thread(client_q.get, timeout=0.5)
                    if not chunk:
                        # Leerer Chunk signalisiert Stream-Ende
                        break
                    yield chunk
                except queue.Empty:
                    # Keine Daten innerhalb des Timeouts, prüfe Disconnect
                    continue
        finally:
            manager.unsubscribe_client(client_q)

    return StreamingResponse(
        stream_generator(),
        media_type="video/mp2t",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "Access-Control-Allow-Origin": "*",
        },
    )


async def api_stream_stop(request: Request) -> JSONResponse:
    """Beendet den aktiven Stream und sendet 0xF8/0x07 an den Dongle."""
    await asyncio.to_thread(manager.stop_stream)
    return JSONResponse({"success": True, "message": "Stream gestoppt"})


# ---------------------------------------------------------------------------
# Aufnahmen & TS-Entschlüsselung
# ---------------------------------------------------------------------------
async def api_record_start(request: Request) -> JSONResponse:
    """Startet Aufnahme des aktuellen oder angegebenen Kanals."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    prog_idx = body.get("prog_idx")
    filename = body.get("filename")
    ok, msg = await asyncio.to_thread(manager.start_recording, prog_idx, filename)
    return JSONResponse({"success": ok, "message": msg})


async def api_record_stop(request: Request) -> JSONResponse:
    """Stoppt die laufende Aufnahme."""
    ok, msg = await asyncio.to_thread(manager.stop_recording)
    return JSONResponse({"success": ok, "message": msg})


async def api_recordings_list(request: Request) -> JSONResponse:
    """Listet alle vorhandenen Aufnahmen auf."""
    recs = await asyncio.to_thread(manager.list_recordings)
    return JSONResponse({"success": True, "recordings": recs})


async def api_recording_file(request: Request) -> Response:
    """Lädt eine gespeicherte Aufnahme herunter oder streamt sie."""
    filename = request.path_params.get("filename")
    safe_name = os.path.basename(filename)
    path = RECORDINGS_DIR / safe_name
    if not path.is_file():
        return Response("Datei nicht gefunden", status_code=404)
    return FileResponse(
        str(path),
        media_type="video/mp2t",
        filename=safe_name,
    )


async def api_recordings_decrypt(request: Request) -> JSONResponse:
    """Entschlüsselt eine ausgewählte .ts-Datei (AES-128-ECB)."""
    try:
        body = await request.json()
        input_file = body.get("path") or body.get("filename")
    except Exception:
        input_file = None

    if not input_file:
        return JSONResponse({"success": False, "message": "Keine Datei angegeben"}, status_code=400)

    target_path = Path(input_file)
    if not target_path.is_file():
        target_path = RECORDINGS_DIR / os.path.basename(input_file)
    if not target_path.is_file():
        return JSONResponse({"success": False, "message": f"Datei nicht gefunden: {input_file}"}, status_code=404)

    t0 = time.perf_counter()
    try:
        out_path = await asyncio.to_thread(decrypt_ts_file, target_path)
        dt = time.perf_counter() - t0
        size_mb = out_path.stat().st_size / 1_048_576
        return JSONResponse({
            "success": True,
            "message": f"Erfolgreich entschlüsselt: {out_path.name} ({size_mb:.2f} MB in {dt:.2f}s = {size_mb/max(dt,0.001):.1f} MB/s)",
            "path": str(out_path),
        })
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Fehler bei Entschlüsselung: {e}"}, status_code=500)


async def api_recording_delete(request: Request) -> JSONResponse:
    """Löscht eine gespeicherte Aufnahme."""
    filename = request.path_params.get("filename", "")
    ok, msg = await asyncio.to_thread(manager.delete_recording, filename)
    return JSONResponse({"success": ok, "message": msg}, status_code=200 if ok else 404)


async def api_timers_list(request: Request) -> JSONResponse:
    """Listet alle programmierten Timer auf."""
    timers = await asyncio.to_thread(manager.list_timers)
    return JSONResponse({"success": True, "timers": timers})


async def api_timers_create(request: Request) -> JSONResponse:
    """Erstellt einen neuen Aufnahme-Timer."""
    try:
        body = await request.json()
        prog_idx = int(body.get("prog_idx"))
        title = body.get("title", "").strip()
        start_time = float(body.get("start_time", 0))
        duration_minutes = int(body.get("duration_minutes", 60))
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ungültige Parameter: {e}"}, status_code=400)

    ok, msg, entry = await asyncio.to_thread(
        manager.add_timer,
        prog_idx=prog_idx,
        title=title,
        start_time=start_time,
        duration_minutes=duration_minutes,
    )
    return JSONResponse({"success": ok, "message": msg, "timer": entry.to_dict() if entry else None})


async def api_timers_delete(request: Request) -> JSONResponse:
    """Löscht einen Timer anhand seiner ID."""
    timer_id = request.path_params.get("timer_id", "")
    ok, msg = await asyncio.to_thread(manager.delete_timer, timer_id)
    return JSONResponse({"success": ok, "message": msg})


# ---------------------------------------------------------------------------
# Tuner & Transponder-Scan
# ---------------------------------------------------------------------------
async def api_tuner_tune(request: Request) -> JSONResponse:
    """Stellt den Tuner auf einen Transponder ein."""
    try:
        body = await request.json()
        freq = int(body.get("freq", 11362))
        sr = int(body.get("sym", 22000))
        pol = body.get("pol", "H").strip().upper()
        sat_lon = int(body.get("sat_lon", 192))
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ungültige Parameter: {e}"}, status_code=400)

    ok, msg = await asyncio.to_thread(manager.tune_transponder, freq, sr, pol, sat_lon)
    return JSONResponse({"success": ok, "message": msg})


async def api_tuner_scan_start(request: Request) -> JSONResponse:
    """Startet den DVB-S2 Sendersuchlauf."""
    try:
        body = await request.json()
        scan_type = int(body.get("scan_type", 0))  # 0=Manual, 1=Auto, 2=Network
        network_scan = bool(body.get("network_scan", False))
        search_range = int(body.get("search_range", 0))  # 0=Alle, 1=FTA, 2=TV, 3=Radio
    except Exception:
        scan_type, network_scan, search_range = 0, False, 0

    ok, msg = await asyncio.to_thread(manager.start_scan, scan_type, network_scan, search_range)
    return JSONResponse({"success": ok, "message": msg})


async def api_tuner_scan_stop(request: Request) -> JSONResponse:
    """Stoppt den laufenden Sendersuchlauf."""
    ok, msg = await asyncio.to_thread(manager.stop_scan)
    return JSONResponse({"success": ok, "message": msg})


# ---------------------------------------------------------------------------
# Diagnose & Werkzeuge
# ---------------------------------------------------------------------------
async def api_probe(request: Request) -> JSONResponse:
    """Sendet einen APIX-Opcode an den Dongle zur Diagnose."""
    try:
        body = await request.json()
        opcode = int(str(body.get("opcode", "0")), 0)
    except Exception:
        return JSONResponse({"success": False, "message": "Ungültiger Opcode"}, status_code=400)

    if not (0x04 <= opcode <= 0x1F):
        return JSONResponse({"success": False, "message": "Opcode muss zwischen 0x04 und 0x1F liegen"}, status_code=400)

    def _do_probe():
        if not manager.tcp_sock:
            sock = protocol.connect(manager.ip)
            if not sock:
                raise ConnectionError("Verbindung fehlgeschlagen")
            try:
                resp = protocol.send_recv(sock, protocol.cmd_probe(opcode), 4, f"probe 0x{opcode:02X}")
                return resp.hex(" ")
            finally:
                protocol.disconnect(sock)
        else:
            with manager.lock:
                resp = protocol.send_recv(manager.tcp_sock, protocol.cmd_probe(opcode), 4, f"probe 0x{opcode:02X}")
            return resp.hex(" ")

    try:
        hex_res = await asyncio.to_thread(_do_probe)
        return JSONResponse({"success": True, "opcode": f"0x{opcode:02X}", "response": hex_res or "(keine Nutzdaten)"})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


async def api_pcap_analyze(request: Request) -> JSONResponse:
    """Analysiert eine PCAP-Datei auf APIX-Befehle und 0xF9/0x0A-Antworten."""
    try:
        body = await request.json()
        pcap_path = body.get("path")
    except Exception:
        pcap_path = None

    if not pcap_path or not Path(pcap_path).is_file():
        return JSONResponse({"success": False, "message": "PCAP-Datei nicht gefunden"}, status_code=404)

    try:
        res = await asyncio.to_thread(pcap_analyze, Path(pcap_path))
        return JSONResponse({"success": True, "result": res})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Analyse-Fehler: {e}"}, status_code=500)


async def api_playlist_m3u(request: Request) -> Response:
    """Generiert eine vollständige M3U-Playlist für VLC, Kodi, Apple TV etc."""
    base_url = str(request.base_url)
    m3u_text = manager.generate_m3u(base_url)
    return Response(
        m3u_text,
        media_type="application/x-mpegurl",
        headers={"Content-Disposition": 'attachment; filename="wisi_channels.m3u"'},
    )


# ---------------------------------------------------------------------------
# HTML Frontend
# ---------------------------------------------------------------------------
_HTML_PAGE = """<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>WISI OR S2D – DVB-over-IP Control Center</title>
  <script src="/static/mpegts.min.js"></script>
  <style>
    :root {
      --bg: #0f141c;
      --card: #18202c;
      --card-hover: #202b3b;
      --border: #29384d;
      --text: #e2e8f0;
      --text-muted: #94a3b8;
      --primary: #38bdf8;
      --primary-hover: #0ea5e9;
      --accent: #10b981;
      --accent-danger: #ef4444;
      --accent-warn: #f59e0b;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--font);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: #111827;
      border-bottom: 1px solid var(--border);
      padding: 12px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 16px;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .logo-group {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .logo-icon {
      background: linear-gradient(135deg, #0284c7, #38bdf8);
      width: 40px;
      height: 40px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 20px;
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.4);
    }
    .logo-text h1 { font-size: 1.15rem; font-weight: 700; color: #fff; }
    .logo-text p { font-size: 0.75rem; color: var(--text-muted); }
    .header-controls {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
    .ip-box {
      display: flex;
      background: #1e293b;
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }
    .ip-box input {
      background: transparent;
      border: none;
      padding: 8px 12px;
      color: #fff;
      font-size: 0.9rem;
      outline: none;
      width: 150px;
    }
    button {
      background: var(--primary);
      color: #0f172a;
      border: none;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s ease;
    }
    button:hover { background: var(--primary-hover); transform: translateY(-1px); }
    button:active { transform: translateY(0); }
    button.secondary {
      background: #334155;
      color: var(--text);
    }
    button.secondary:hover { background: #475569; }
    button.danger {
      background: var(--accent-danger);
      color: #fff;
    }
    button.danger:hover { background: #dc2626; }
    button.success {
      background: var(--accent);
      color: #fff;
    }
    button.success:hover { background: #059669; }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 20px;
      font-size: 0.75rem;
      font-weight: 600;
      background: #334155;
    }
    .badge.connected { background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }
    .badge.disconnected { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }
    .signal-gauges {
      display: flex;
      align-items: center;
      gap: 16px;
      background: #1e293b;
      padding: 6px 14px;
      border-radius: 8px;
      border: 1px solid var(--border);
    }
    .gauge { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; }
    .gauge-bar-bg {
      width: 70px;
      height: 8px;
      background: #334155;
      border-radius: 4px;
      overflow: hidden;
    }
    .gauge-bar-val {
      height: 100%;
      background: var(--accent);
      width: 0%;
      transition: width 0.4s ease;
    }
    nav.tabs {
      background: #111827;
      border-bottom: 1px solid var(--border);
      padding: 0 24px;
      display: flex;
      gap: 8px;
      overflow-x: auto;
    }
    .tab-btn {
      background: transparent;
      color: var(--text-muted);
      border-radius: 0;
      border-bottom: 3px solid transparent;
      padding: 12px 16px;
      font-size: 0.9rem;
      font-weight: 500;
    }
    .tab-btn:hover { background: rgba(255,255,255,0.03); color: var(--text); transform: none; }
    .tab-btn.active {
      color: var(--primary);
      border-bottom-color: var(--primary);
      background: transparent;
    }
    main {
      flex: 1;
      padding: 24px;
      max-width: 1440px;
      margin: 0 auto;
      width: 100%;
    }
    .tab-pane { display: none; }
    .tab-pane.active { display: block; animation: fadeIn 0.2s ease; }
    @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }

    /* Player Layout */
    .tv-layout {
      display: grid;
      grid-template-columns: 420px 1fr;
      gap: 24px;
    }
    @media (max-width: 1024px) {
      .tv-layout { grid-template-columns: 1fr; }
    }
    .player-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      overflow: hidden;
      display: flex;
      flex-direction: column;
    }
    .video-container {
      background: #000;
      width: 100%;
      aspect-ratio: 16 / 9;
      position: relative;
    }
    video {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
    .player-info {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .player-title {
      font-size: 1.1rem;
      font-weight: 700;
      color: #fff;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .stream-metrics {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      background: #0f172a;
      padding: 10px;
      border-radius: 8px;
      font-size: 0.75rem;
      color: var(--text-muted);
    }
    .stream-metrics strong { color: var(--text); display: block; font-size: 0.9rem; }
    .player-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }

    /* Channels section */
    .channels-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .channels-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }
    .search-filter-box {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      flex: 1;
    }
    .search-input {
      background: #1e293b;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 14px;
      color: #fff;
      font-size: 0.85rem;
      outline: none;
      min-width: 200px;
    }
    .filter-pills {
      display: flex;
      gap: 6px;
    }
    .filter-pill {
      background: #1e293b;
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 20px;
      font-size: 0.75rem;
      color: var(--text-muted);
      cursor: pointer;
    }
    .filter-pill.active {
      background: var(--primary);
      color: #0f172a;
      border-color: var(--primary);
      font-weight: 600;
    }
    .channels-table-wrapper {
      max-height: 650px;
      overflow-y: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 0.85rem;
    }
    th {
      background: #111827;
      color: var(--text-muted);
      padding: 10px 14px;
      font-weight: 600;
      position: sticky;
      top: 0;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 10px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.05);
    }
    tr:hover td { background: var(--card-hover); }
    .ch-name { font-weight: 600; color: #fff; }
    .ch-epg { font-size: 0.75rem; color: var(--text-muted); margin-top: 2px; }
    .tag {
      font-size: 0.7rem;
      padding: 2px 6px;
      border-radius: 4px;
      font-weight: 600;
    }
    .tag.fta { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .tag.enc { background: rgba(239, 68, 68, 0.2); color: #f87171; }
    .tag.tv { background: rgba(56, 189, 248, 0.2); color: #38bdf8; }
    .tag.radio { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }

    /* EPG Grid */
    .epg-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }
    .epg-card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .epg-card h3 { font-size: 1rem; color: #fff; display: flex; justify-content: space-between; }
    .epg-event-item {
      background: #1e293b;
      padding: 10px;
      border-radius: 6px;
      font-size: 0.8rem;
    }
    .epg-time { color: var(--primary); font-weight: 600; margin-bottom: 4px; }
    .epg-desc { color: var(--text-muted); font-size: 0.75rem; }

    /* Tuner & Scanner */
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 24px;
    }
    @media (max-width: 768px) {
      .grid-2 { grid-template-columns: 1fr; }
    }
    .form-group {
      display: flex;
      flex-direction: column;
      gap: 6px;
      margin-bottom: 14px;
    }
    label { font-size: 0.8rem; color: var(--text-muted); font-weight: 500; }
    input[type="text"], input[type="number"], select {
      background: #1e293b;
      border: 1px solid var(--border);
      color: #fff;
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.85rem;
      outline: none;
    }
    .scan-progress-box {
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px;
      margin-top: 16px;
    }

    /* Toast */
    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #1e293b;
      border: 1px solid var(--primary);
      color: #fff;
      padding: 12px 20px;
      border-radius: 8px;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      z-index: 1000;
      display: none;
      font-size: 0.85rem;
    }
  </style>
</head>
<body>
  <header>
    <div class="logo-group">
      <div class="logo-icon">📡</div>
      <div class="logo-text">
        <h1>WISI OR S2D</h1>
        <p>DVB-S2 DVB-over-IP Control Center</p>
      </div>
    </div>

    <div class="header-controls">
      <div class="ip-box">
        <input type="text" id="dongleIpInput" value="192.168.178.32" placeholder="Dongle IP">
      </div>
      <button id="btnConnect" onclick="connectDongle()">Verbinden</button>
      <button id="btnDiscover" class="secondary" onclick="discoverDongle()">🔍 Suchen</button>
      <div id="connBadge" class="badge disconnected">● Getrennt</div>

      <div class="signal-gauges">
        <div class="gauge">
          <span>Stärke:</span>
          <div class="gauge-bar-bg"><div id="gaugeAgc" class="gauge-bar-val"></div></div>
          <span id="valAgc">0%</span>
        </div>
        <div class="gauge">
          <span>Qualität:</span>
          <div class="gauge-bar-bg"><div id="gaugeSnr" class="gauge-bar-val"></div></div>
          <span id="valSnr">0%</span>
        </div>
        <div id="gaugeLock" class="badge">❌ Kein Signal</div>
      </div>
    </div>
  </header>

  <nav class="tabs">
    <button class="tab-btn active" onclick="switchTab('tv')">📺 Live TV & Kanäle</button>
    <button class="tab-btn" onclick="switchTab('epg')">📅 Programmführer (EPG)</button>
    <button class="tab-btn" onclick="switchTab('tuner')">📡 Tuner & Suchlauf</button>
    <button class="tab-btn" onclick="switchTab('recordings')">📼 Aufnahmen & Timer</button>
    <button class="tab-btn" onclick="switchTab('info')">ℹ️ Dongle Info</button>
    <button class="tab-btn" onclick="switchTab('tools')">🛠️ PCAP & Werkzeuge</button>
  </nav>

  <main>
    <!-- TAB 1: LIVE TV & CHANNELS -->
    <div id="tab-tv" class="tab-pane active">
      <div class="tv-layout">
        <!-- Player -->
        <div class="player-card">
          <div class="video-container">
            <video id="videoElement" controls autoplay muted playsinline></video>
          </div>
          <div class="player-info">
            <div class="player-title">
              <span id="playerChannelName">Kein Kanal aktiv</span>
              <span id="playerFtaBadge" class="tag fta">FTA</span>
            </div>
            <div class="stream-metrics">
              <div>Bitrate<strong id="metricBitrate">0 KB/s</strong></div>
              <div>Empfangen<strong id="metricBytes">0 MB</strong></div>
              <div>Dauer<strong id="metricDuration">00:00</strong></div>
            </div>
            <div class="player-actions">
              <button class="secondary" onclick="copyStreamUrl()">📋 Stream-URL</button>
              <button class="secondary" onclick="openInVlc()">▶️ In VLC abspielen</button>
              <button id="btnRecPlayer" class="danger" onclick="toggleRecording()">🔴 Aufnahme</button>
              <button class="secondary" onclick="stopStream()">⏹️ Stopp</button>
            </div>
          </div>
        </div>

        <!-- Channels List -->
        <div class="channels-card">
          <div class="channels-header">
            <div class="search-filter-box">
              <input type="text" id="channelSearch" class="search-input" placeholder="Sender suchen..." oninput="renderChannels()">
              <div class="filter-pills">
                <div class="filter-pill active" onclick="setFilter('all', this)">Alle</div>
                <div class="filter-pill" onclick="setFilter('tv', this)">TV</div>
                <div class="filter-pill" onclick="setFilter('radio', this)">Radio</div>
                <div class="filter-pill" onclick="setFilter('fta', this)">FTA</div>
                <div class="filter-pill" onclick="setFilter('enc', this)">🔒 Verschlüsselt</div>
              </div>
            </div>
            <div style="display:flex; gap:8px;">
              <button class="secondary" onclick="refreshChannels()">🔄 Neu laden</button>
              <a href="/playlist.m3u" download="wisi.m3u" style="text-decoration:none;">
                <button class="secondary">📥 M3U Playlist</button>
              </a>
            </div>
          </div>

          <div class="channels-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th style="width:50px;">LCN</th>
                  <th>Sender</th>
                  <th style="width:70px;">Typ</th>
                  <th style="width:140px;">Frequenz</th>
                  <th style="width:80px;">Status</th>
                  <th style="width:120px;">Aktion</th>
                </tr>
              </thead>
              <tbody id="channelsTableBody">
                <tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Lade Kanalliste...</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 2: EPG -->
    <div id="tab-epg" class="tab-pane">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:16px;">
        <h2>Elektronischer Programmführer (EPG)</h2>
        <button onclick="refreshEpg()">🔄 EPG vom Dongle laden</button>
      </div>
      <div id="epgGrid" class="epg-grid">
        <p style="color:var(--text-muted);">Lade EPG-Daten...</p>
      </div>
    </div>

    <!-- TAB 3: TUNER & SCAN -->
    <div id="tab-tuner" class="tab-pane">
      <div class="grid-2">
        <div class="channels-card">
          <h3>Transponder einstellen (Tuning)</h3>
          <div class="form-group">
            <label>Frequenz (MHz)</label>
            <input type="number" id="tuneFreq" value="11362">
          </div>
          <div class="form-group">
            <label>Polarisation</label>
            <select id="tunePol">
              <option value="H" selected>Horizontal (18V)</option>
              <option value="V">Vertikal (13V)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Symbolrate (kS/s)</label>
            <input type="number" id="tuneSr" value="22000">
          </div>
          <div class="form-group">
            <label>Satellit Orbit-Position (0.1°)</label>
            <input type="number" id="tuneSat" value="192" title="192 = Astra 19.2° Ost">
          </div>
          <button class="success" onclick="tuneTransponder()">📡 Transponder einstellen</button>
        </div>

        <div class="channels-card">
          <h3>DVB-S2 Sendersuchlauf</h3>
          <div class="form-group">
            <label>Suchlauf-Modus</label>
            <select id="scanMode">
              <option value="0">Manuell (Transponder)</option>
              <option value="1">Auto (Vollständig)</option>
              <option value="2">Netzwerk (NIT)</option>
            </select>
          </div>
          <div class="form-group">
            <label>Suchfilter</label>
            <select id="scanFilter">
              <option value="0">Alle Sender</option>
              <option value="1">Nur Free-To-Air (FTA)</option>
              <option value="2">Nur Fernsehen (TV)</option>
              <option value="3">Nur Radio</option>
            </select>
          </div>
          <div style="display:flex; gap:10px;">
            <button class="primary" onclick="startScan()">🔍 Suchlauf starten</button>
            <button class="danger" onclick="stopScan()">⏹️ Abbrechen</button>
          </div>

          <div id="scanBox" class="scan-progress-box" style="display:none;">
            <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
              <span>Suchlauf-Fortschritt</span>
              <strong id="scanProgressText">0%</strong>
            </div>
            <div class="gauge-bar-bg" style="width:100%; height:12px; margin-bottom:12px;">
              <div id="scanProgressBar" class="gauge-bar-val" style="width:0%;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:0.85rem;">
              <span>📺 TV gefunden: <strong id="scanTvCount">0</strong></span>
              <span>📻 Radio gefunden: <strong id="scanRadioCount">0</strong></span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TAB 4: RECORDINGS & TIMERS -->
    <div id="tab-recordings" class="tab-pane">
      <div class="grid-2">
        <!-- LINKER BEREICH: TIMER & PROGRAMMIERUNG -->
        <div class="channels-card">
          <h3>⏰ Aufnahme planen (Timer)</h3>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:12px;">
            Programmiere automatische Aufnahmen. Der Server nimmt den gewählten Sender zur Startzeit im Hintergrund auf.
          </p>
          <div class="form-group">
            <label>Sender auswählen</label>
            <select id="timerChannelSelect">
              <option value="">Lade Senderliste...</option>
            </select>
          </div>
          <div class="form-group">
            <label>Titel der Sendung</label>
            <input type="text" id="timerTitleInput" placeholder="z. B. Tagesschau, Spielfilm, Doku">
          </div>
          <div style="display:flex; gap:10px;">
            <div class="form-group" style="flex:2;">
              <label>Startzeit</label>
              <input type="datetime-local" id="timerStartInput">
            </div>
            <div class="form-group" style="flex:1;">
              <label>Dauer (Minuten)</label>
              <input type="number" id="timerDurationInput" value="60" min="1" max="600">
            </div>
          </div>
          <button class="primary" onclick="createTimer()">⏰ Aufnahme programmieren</button>

          <h4 style="margin-top:24px; margin-bottom:8px;">Geplante & aktive Timer</h4>
          <div id="timersList">
            <p style="color:var(--text-muted); font-size:0.85rem;">Lade Timer...</p>
          </div>
        </div>

        <!-- RECHTER BEREICH: GESPEICHERTE AUFNAHMEN -->
        <div class="channels-card">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <h3 style="margin:0;">📼 Gespeicherte Aufnahmen</h3>
            <button class="secondary" style="font-size:0.75rem; padding:4px 8px;" onclick="loadRecordings()">🔄 Aktualisieren</button>
          </div>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:12px;">
            Alle Aufnahmen liegen als unverschlüsselte MPEG-TS Dateien vor und können direkt im Web-Player abgespielt werden.
          </p>
          <div id="recordingsList">
            <p style="color:var(--text-muted);">Lade Aufnahmen...</p>
          </div>

          <hr style="border:0; border-top:1px solid var(--border); margin:20px 0;">

          <h4>TS-Datei nachträglich entschlüsseln</h4>
          <p style="font-size:0.85rem; color:var(--text-muted); margin-bottom:10px;">
            Für manuell kopierte Roh-Dateien (AES-128-ECB Link-Entschlüsselung):
          </p>
          <div class="form-group">
            <input type="text" id="decryptPathInput" placeholder="z. B. recordings/stream.ts">
          </div>
          <button class="secondary" onclick="decryptFile()">🔓 Manuell entschlüsseln</button>
          <div id="decryptResult" style="margin-top:10px; font-size:0.85rem;"></div>
        </div>
      </div>
    </div>

    <!-- TAB 5: DONGLE INFO -->
    <div id="tab-info" class="tab-pane">
      <div class="channels-card">
        <h3>Hardware- & Firmware-Details (Phase 1–3)</h3>
        <div id="infoTable" style="margin-top:12px;">
          <p style="color:var(--text-muted);">Lade Hardware-Informationen...</p>
        </div>
      </div>
    </div>

    <!-- TAB 6: TOOLS & PCAP -->
    <div id="tab-tools" class="tab-pane">
      <div class="grid-2">
        <div class="channels-card">
          <h3>APIX-Opcode Tester</h3>
          <div class="form-group">
            <label>Opcode (z. B. 0x12)</label>
            <input type="text" id="probeOpcodeInput" value="0x12">
          </div>
          <button class="primary" onclick="probeOpcode()">⚡ Opcode testen</button>
          <div id="probeResult" style="margin-top:12px; font-family:monospace; font-size:0.85rem;"></div>
        </div>

        <div class="channels-card">
          <h3>PCAP Analyzer</h3>
          <div class="form-group">
            <label>PCAP-Dateipfad</label>
            <input type="text" id="pcapPathInput" placeholder="research/assets/PCAPdroid_12_Okt._16_16_04.pcap">
          </div>
          <button class="primary" onclick="analyzePcap()">📊 PCAP analysieren</button>
          <pre id="pcapResult" style="margin-top:12px; background:#0f172a; padding:12px; border-radius:6px; font-size:0.75rem; max-height:300px; overflow:auto;"></pre>
        </div>
      </div>
    </div>
  </main>

  <div id="toast"></div>

  <script>
    let currentChannels = [];
    let currentFilter = 'all';
    let activeProgIdx = null;
    let player = null;
    let pollInterval = null;

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.innerText = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 3500);
    }

    function switchTab(tabId) {
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
      const targetPane = document.getElementById('tab-' + tabId);
      if (targetPane) targetPane.classList.add('active');
      const targetBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick') && b.getAttribute('onclick').includes(tabId));
      if (targetBtn) targetBtn.classList.add('active');
      if (tabId === 'recordings') {
        loadRecordings();
        loadTimers();
        populateTimerChannels();
      }
      if (tabId === 'info') loadInfo();
      if (tabId === 'epg') loadEpg();
    }

    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        
        // Connection badge
        const badge = document.getElementById('connBadge');
        if (data.connected) {
          badge.className = 'badge connected';
          badge.innerText = '● Verbunden (' + data.ip + ')';
        } else {
          badge.className = 'badge disconnected';
          badge.innerText = '● Getrennt';
        }

        // Signal Gauges
        document.getElementById('gaugeAgc').style.width = data.signal.strength + '%';
        document.getElementById('valAgc').innerText = data.signal.strength + '%';
        document.getElementById('gaugeSnr').style.width = data.signal.quality + '%';
        document.getElementById('valSnr').innerText = data.signal.quality + '%';

        const lockBadge = document.getElementById('gaugeLock');
        if (data.signal.locked) {
          lockBadge.className = 'badge connected';
          lockBadge.innerText = '🔒 Gelockt';
        } else {
          lockBadge.className = 'badge';
          lockBadge.innerText = '❌ Kein Lock';
        }

        // Streaming metrics
        if (data.streaming && data.streaming.is_streaming) {
          document.getElementById('metricBitrate').innerText = data.streaming.kbps + ' KB/s';
          document.getElementById('metricBytes').innerText = (data.streaming.bytes / 1048576).toFixed(1) + ' MB';
          const dur = Math.round(data.streaming.elapsed || 0);
          const m = String(Math.floor(dur / 60)).padStart(2, '0');
          const s = String(dur % 60).padStart(2, '0');
          document.getElementById('metricDuration').innerText = m + ':' + s;
        }

        // Recording button state
        const recBtn = document.getElementById('btnRecPlayer');
        if (data.recording && data.recording.active) {
          recBtn.className = 'danger';
          recBtn.innerText = '⏹️ Aufnahme stoppen (' + Math.round(data.recording.seconds) + 's)';
        } else {
          recBtn.className = 'secondary';
          recBtn.innerText = '🔴 Aufnahme';
        }

        // Scan progress
        if (data.scan && data.scan.in_progress) {
          document.getElementById('scanBox').style.display = 'block';
          document.getElementById('scanProgressBar').style.width = data.scan.progress + '%';
          document.getElementById('scanProgressText').innerText = data.scan.progress + '%';
          document.getElementById('scanTvCount').innerText = data.scan.tv_count;
          document.getElementById('scanRadioCount').innerText = data.scan.radio_count;
        }
      } catch (err) {}
    }

    async function connectDongle() {
      const ip = document.getElementById('dongleIpInput').value.trim();
      showToast('Verbinde mit ' + ip + ' …');
      const res = await fetch('/api/connect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ip })
      });
      const data = await res.json();
      showToast(data.message);
      loadChannels();
      pollStatus();
    }

    async function discoverDongle() {
      showToast('Suche WISI Dongle per Broadcast…');
      const res = await fetch('/api/discover', { method: 'POST' });
      const data = await res.json();
      if (data.devices && data.devices.length > 0) {
        document.getElementById('dongleIpInput').value = data.devices[0].ip;
        showToast('Gefunden: ' + data.devices[0].ip);
      } else {
        showToast('Kein Dongle per Broadcast gefunden – nutze Standard-IP.');
      }
    }

    async function loadChannels() {
      try {
        const res = await fetch('/api/channels');
        const data = await res.json();
        currentChannels = data.channels || [];
        renderChannels();
      } catch (e) {
        console.error(e);
      }
    }

    async function refreshChannels() {
      showToast('Lade Kanalliste frisch vom Dongle…');
      const res = await fetch('/api/channels/refresh', { method: 'POST' });
      const data = await res.json();
      showToast(data.message);
      loadChannels();
    }

    function setFilter(filt, el) {
      currentFilter = filt;
      document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
      el.classList.add('active');
      renderChannels();
    }

    function renderChannels() {
      const q = document.getElementById('channelSearch').value.toLowerCase().trim();
      const tbody = document.getElementById('channelsTableBody');
      const filtered = currentChannels.filter(c => {
        if (currentFilter === 'tv' && c.is_radio) return false;
        if (currentFilter === 'radio' && !c.is_radio) return false;
        if (currentFilter === 'fta' && !c.fta) return false;
        if (currentFilter === 'enc' && c.fta) return false;
        if (q) {
          const matchName = c.name.toLowerCase().includes(q);
          const matchLcn = String(c.lcn).includes(q);
          const matchSid = String(c.service_id).includes(q);
          return matchName || matchLcn || matchSid;
        }
        return true;
      });

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center; color:var(--text-muted);">Keine Sender gefunden.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(c => `
        <tr>
          <td><strong style="color:var(--text);">${c.lcn || '-'}</strong></td>
          <td>
            <div class="ch-name">${c.name}</div>
            <div class="ch-epg">${c.current_show ? '▶ ' + c.current_show : 'SID ' + c.service_id}</div>
          </td>
          <td><span class="tag ${c.is_radio ? 'radio' : 'tv'}">${c.is_radio ? 'Radio' : 'TV'}</span></td>
          <td>${c.freq} MHz ${c.pol}</td>
          <td><span class="tag ${c.fta ? 'fta' : 'enc'}">${c.fta ? 'FTA' : '🔒 Verschlüsselt'}</span></td>
          <td>
            <button onclick="playChannel(${c.prog_idx}, '${c.name.replace(/'/g, "\\'")}', ${c.fta})">▶ Play</button>
          </td>
        </tr>
      `).join('');
    }

    function playChannel(progIdx, name, fta) {
      activeProgIdx = progIdx;
      document.getElementById('playerChannelName').innerText = name;
      const ftaBadge = document.getElementById('playerFtaBadge');
      ftaBadge.className = 'tag ' + (fta ? 'fta' : 'enc');
      ftaBadge.innerText = fta ? 'FTA' : '🔒 Pay-TV';

      const videoElement = document.getElementById('videoElement');
      const streamUrl = window.location.origin + '/api/stream/' + progIdx;

      if (mpegts.getFeatureList().mseLivePlayback) {
        if (player) {
          player.pause();
          player.unload();
          player.detachMediaElement();
          player.destroy();
          player = null;
        }

        player = mpegts.createPlayer({
          type: 'mse',
          isLive: true,
          url: streamUrl
        }, {
          enableWorker: true,
          lazyLoad: false,
          liveBufferLatencyChasing: true
        });

        player.attachMediaElement(videoElement);
        player.load();
        player.play().catch(e => console.log('Autoplay:', e));
      } else {
        videoElement.src = streamUrl;
        videoElement.play().catch(e => console.log('Autoplay:', e));
      }
      showToast('Kanal gewählt: ' + name);
    }

    async function stopStream() {
      if (player) {
        player.pause();
        player.unload();
      }
      await fetch('/api/stream/stop', { method: 'POST' });
      document.getElementById('playerChannelName').innerText = 'Kein Kanal aktiv';
      showToast('Stream gestoppt.');
    }

    function copyStreamUrl() {
      if (!activeProgIdx) { showToast('Erst Kanal auswählen.'); return; }
      const url = window.location.origin + '/api/stream/' + activeProgIdx;
      navigator.clipboard.writeText(url);
      showToast('Stream-URL in Zwischenablage kopiert: ' + url);
    }

    function openInVlc() {
      if (!activeProgIdx) { showToast('Erst Kanal auswählen.'); return; }
      const url = window.location.origin + '/api/stream/' + activeProgIdx;
      window.location.href = 'vlc://' + url;
      showToast('Öffne VLC mit: ' + url);
    }

    async function toggleRecording() {
      const res = await fetch('/api/status');
      const st = await res.json();
      if (st.recording && st.recording.active) {
        const r = await fetch('/api/record/stop', { method: 'POST' });
        const d = await r.json();
        showToast(d.message);
      } else {
        const r = await fetch('/api/record/start', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ prog_idx: activeProgIdx })
        });
        const d = await r.json();
        showToast(d.message);
      }
    }

    async function loadRecordings() {
      const res = await fetch('/api/recordings');
      const data = await res.json();
      const div = document.getElementById('recordingsList');
      if (!data.recordings || data.recordings.length === 0) {
        div.innerHTML = '<p style="color:var(--text-muted);">Keine Aufnahmen vorhanden.</p>';
        return;
      }
      div.innerHTML = data.recordings.map(r => `
        <div style="background:#1e293b; padding:12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
          <div>
            <div style="font-weight:600; color:#fff;">${r.filename}</div>
            <div style="font-size:0.75rem; color:var(--text-muted);">${r.size_mb} MB • ${r.created}</div>
          </div>
          <div style="display:flex; gap:6px; flex-wrap:wrap;">
            <button class="primary" style="font-size:0.75rem; padding:4px 8px;" onclick="playRecordedFile('${r.filename.replace(/'/g, "\\'")}')">▶️ Abspielen</button>
            <a href="/api/recordings/${encodeURIComponent(r.filename)}" download>
              <button class="secondary" style="font-size:0.75rem; padding:4px 8px;">📥 Download</button>
            </a>
            <button class="secondary" style="font-size:0.75rem; padding:4px 8px;" onclick="setDecryptPath('${r.path.replace(/\\\\/g, '/')}')">🔓 Entschlüsseln</button>
            <button class="danger" style="font-size:0.75rem; padding:4px 8px;" onclick="deleteRecording('${r.filename.replace(/'/g, "\\'")}')">🗑️ Löschen</button>
          </div>
        </div>
      `).join('');
    }

    function playRecordedFile(filename) {
      if (player) {
        player.pause();
        player.unload();
        player.detachMediaElement();
        player.destroy();
        player = null;
      }
      activeProgIdx = 0;
      document.getElementById('playerChannelName').innerText = '📼 Aufnahme: ' + filename;
      const ftaBadge = document.getElementById('playerFtaBadge');
      ftaBadge.className = 'tag fta';
      ftaBadge.innerText = 'Aufnahme';

      const videoElement = document.getElementById('videoElement');
      const fileUrl = window.location.origin + '/api/recordings/' + encodeURIComponent(filename);

      if (typeof mpegts !== 'undefined' && mpegts.isSupported()) {
        player = mpegts.createPlayer({
          type: 'mse',
          isLive: false,
          url: fileUrl
        }, {
          enableWorker: true,
          lazyLoad: false
        });
        player.attachMediaElement(videoElement);
        player.load();
        player.play().catch(e => console.log('Wiedergabe:', e));
      } else {
        videoElement.src = fileUrl;
        videoElement.play().catch(e => console.log('Wiedergabe:', e));
      }
      switchTab('tv');
      showToast('Spiele Aufnahme: ' + filename);
    }

    async function deleteRecording(filename) {
      if (!confirm('Aufnahme wirklich löschen: ' + filename + '?')) return;
      const res = await fetch('/api/recordings/' + encodeURIComponent(filename), { method: 'DELETE' });
      const data = await res.json();
      showToast(data.message);
      loadRecordings();
    }

    async function loadTimers() {
      const res = await fetch('/api/timers');
      const data = await res.json();
      const div = document.getElementById('timersList');
      if (!div) return;
      if (!data.timers || data.timers.length === 0) {
        div.innerHTML = '<p style="color:var(--text-muted); font-size:0.85rem;">Keine programmierten Timer vorhanden.</p>';
        return;
      }
      div.innerHTML = data.timers.map(t => {
        let statusBadge = '<span class="tag" style="background:#3b82f6;">Geplant</span>';
        if (t.status === 'recording') statusBadge = '<span class="tag" style="background:#ef4444; animation:pulse 1s infinite;">🔴 Nimmt auf</span>';
        if (t.status === 'completed') statusBadge = '<span class="tag fta">Beendet</span>';
        if (t.status === 'failed') statusBadge = '<span class="tag enc">Fehler</span>';
        if (t.status === 'expired') statusBadge = '<span class="tag" style="background:#6b7280;">Abgelaufen</span>';

        return `
          <div style="background:#1e293b; padding:10px 12px; border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;">
            <div>
              <div style="font-weight:600; color:#fff; display:flex; align-items:center; gap:8px;">
                ${t.title} ${statusBadge}
              </div>
              <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">
                ${t.channel_name} • Start: ${t.start_str} • ${t.duration_minutes} Min
              </div>
            </div>
            <div>
              <button class="danger" style="font-size:0.75rem; padding:4px 8px;" onclick="deleteTimer('${t.id}')">🗑️ Löschen</button>
            </div>
          </div>
        `;
      }).join('');
    }

    function populateTimerChannels() {
      const sel = document.getElementById('timerChannelSelect');
      if (!sel) return;
      if (currentChannels.length === 0) {
        sel.innerHTML = '<option value="">Keine Sender geladen (erst Senderliste laden)</option>';
        return;
      }
      sel.innerHTML = currentChannels.map(c => `
        <option value="${c.prog_idx}">${c.name} (${c.is_radio ? 'Radio' : 'TV'}, ${c.fta ? 'FTA' : 'Pay-TV'})</option>
      `).join('');

      const startInp = document.getElementById('timerStartInput');
      if (startInp && !startInp.value) {
        const inFiveMins = new Date(Date.now() + 5 * 60 * 1000);
        inFiveMins.setSeconds(0, 0);
        const tzOffset = inFiveMins.getTimezoneOffset() * 60000;
        const localISOTime = (new Date(inFiveMins - tzOffset)).toISOString().slice(0, 16);
        startInp.value = localISOTime;
      }
    }

    async function createTimer() {
      const progIdx = parseInt(document.getElementById('timerChannelSelect').value, 10);
      const title = document.getElementById('timerTitleInput').value.trim();
      const startVal = document.getElementById('timerStartInput').value;
      const dur = parseInt(document.getElementById('timerDurationInput').value, 10) || 60;

      if (!progIdx) { showToast('Bitte einen Sender auswählen.'); return; }
      if (!startVal) { showToast('Bitte eine Startzeit angeben.'); return; }

      const startTs = new Date(startVal).getTime() / 1000;
      if (isNaN(startTs)) { showToast('Ungültiges Datum'); return; }

      const res = await fetch('/api/timers', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          prog_idx: progIdx,
          title: title || 'Aufnahme',
          start_time: startTs,
          duration_minutes: dur
        })
      });
      const data = await res.json();
      showToast(data.message);
      if (data.success) {
        document.getElementById('timerTitleInput').value = '';
        loadTimers();
      }
    }

    async function deleteTimer(timerId) {
      if (!confirm('Diesen Timer wirklich löschen?')) return;
      const res = await fetch('/api/timers/' + encodeURIComponent(timerId), { method: 'DELETE' });
      const data = await res.json();
      showToast(data.message);
      loadTimers();
    }

    function setDecryptPath(path) {
      document.getElementById('decryptPathInput').value = path;
      showToast('Datei für Entschlüsselung gewählt.');
    }

    async function decryptFile() {
      const p = document.getElementById('decryptPathInput').value.trim();
      if (!p) { showToast('Pfad angeben.'); return; }
      showToast('Entschlüssele Datei…');
      const res = await fetch('/api/recordings/decrypt', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path: p })
      });
      const data = await res.json();
      document.getElementById('decryptResult').innerHTML = `
        <div style="padding:10px; border-radius:6px; background:${data.success ? 'rgba(16,185,129,0.2)' : 'rgba(239,68,68,0.2)'}; color:${data.success ? '#34d399' : '#f87171'};">
          ${data.message}
        </div>
      `;
    }

    async function loadInfo() {
      const res = await fetch('/api/info');
      const data = await res.json();
      const div = document.getElementById('infoTable');
      const info = data.info || {};
      div.innerHTML = `
        <table style="max-width:600px;">
          <tr><td>Modellname:</td><td><strong>${info.model_name || 'WISI OR S2D'}</strong></td></tr>
          <tr><td>Tuner-Typ:</td><td>${info.tuner_name || 'DVB-S2'} (${info.tuner_type || 26})</td></tr>
          <tr><td>SVN-Revision:</td><td>${info.svn_revision || '-'}</td></tr>
          <tr><td>Hardware-Version:</td><td>${info.hw_version || '-'}</td></tr>
          <tr><td>Software-Version:</td><td>${info.sw_version || '-'}</td></tr>
          <tr><td>Loader-Version:</td><td>${info.loader_version || '-'}</td></tr>
          <tr><td>Dongle MAC-Adresse:</td><td>${info.dongle_mac || '-'}</td></tr>
          <tr><td>Dongle IP-Adresse:</td><td>${info.dongle_ip || '-'}</td></tr>
          <tr><td>Client IP-Adresse:</td><td>${info.client_ip || '-'}</td></tr>
          <tr><td>CAS-Typ:</td><td>${info.cas_type || '-'}</td></tr>
          <tr><td>Seriennummer:</td><td><code>${info.serial_id || '-'}</code></td></tr>
          <tr><td>Chip-ID:</td><td><code>${info.chip_id || '-'}</code></td></tr>
        </table>
      `;
    }

    async function loadEpg() {
      const res = await fetch('/api/epg');
      const data = await res.json();
      const grid = document.getElementById('epgGrid');
      const epg = data.epg || {};
      const sids = Object.keys(epg);
      if (sids.length === 0) {
        grid.innerHTML = '<p style="color:var(--text-muted);">Keine EPG-Daten im Speicher. Klicke auf "EPG vom Dongle laden".</p>';
        return;
      }
      grid.innerHTML = sids.map(sid => {
        const events = epg[sid] || [];
        const ch = currentChannels.find(c => c.service_id == sid) || { name: 'SID ' + sid };
        return `
          <div class="epg-card">
            <h3>${ch.name} <span class="tag fta">SID ${sid}</span></h3>
            ${events.slice(0, 4).map(ev => `
              <div class="epg-event-item" style="display:flex; justify-content:space-between; align-items:center; gap:8px;">
                <div>
                  <div class="epg-time">${ev.date} ${ev.time} (${ev.duration})</div>
                  <div style="font-weight:600; color:#fff;">${ev.title}</div>
                </div>
                <button class="secondary" style="font-size:0.75rem; padding:4px 8px; white-space:nowrap;" onclick="scheduleFromEpg(${sid}, '${ch.name.replace(/'/g, "\\'")}', '${ev.title.replace(/'/g, "\\'")}', '${ev.date}', '${ev.time}', '${ev.duration}')">⏰ Aufnehmen</button>
              </div>
            `).join('')}
          </div>
        `;
      }).join('');
    }

    async function scheduleFromEpg(sid, chName, title, dateStr, timeStr, durStr) {
      const ch = currentChannels.find(c => c.service_id == sid);
      const progIdx = ch ? ch.prog_idx : 0;
      if (!progIdx) {
        showToast('Kanal nicht gefunden (Senderliste laden).');
        return;
      }
      let startTs = 0;
      try {
        const dt = new Date(`${dateStr}T${timeStr}:00`);
        if (!isNaN(dt.getTime())) {
          startTs = dt.getTime() / 1000;
        }
      } catch (e) {}
      if (!startTs || startTs < Date.now() / 1000) {
        startTs = Math.floor(Date.now() / 1000);
      }
      let durationMins = 60;
      if (durStr && durStr.includes(':')) {
        const parts = durStr.split(':');
        durationMins = (parseInt(parts[0], 10) * 60) + parseInt(parts[1], 10);
      }
      showToast('Programmiere Timer für ' + title + '…');
      const res = await fetch('/api/timers', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          prog_idx: progIdx,
          title: title || (chName + ' Sendung'),
          start_time: startTs,
          duration_minutes: durationMins
        })
      });
      const data = await res.json();
      showToast(data.message);
    }

    async function refreshEpg() {
      showToast('Lade EPG vom Dongle…');
      const res = await fetch('/api/epg/refresh', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ limit: 25 })
      });
      const data = await res.json();
      showToast(data.message);
      loadEpg();
    }

    async function tuneTransponder() {
      const freq = document.getElementById('tuneFreq').value;
      const pol = document.getElementById('tunePol').value;
      const sym = document.getElementById('tuneSr').value;
      const sat_lon = document.getElementById('tuneSat').value;
      showToast('Stelle Transponder ein…');
      const res = await fetch('/api/tuner/tune', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ freq, pol, sym, sat_lon })
      });
      const data = await res.json();
      showToast(data.message);
    }

    async function startScan() {
      const scan_type = document.getElementById('scanMode').value;
      const search_range = document.getElementById('scanFilter').value;
      showToast('Starte Sendersuchlauf…');
      const res = await fetch('/api/tuner/scan/start', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ scan_type, search_range, network_scan: scan_type == '2' })
      });
      const data = await res.json();
      showToast(data.message);
      document.getElementById('scanBox').style.display = 'block';
    }

    async function stopScan() {
      const res = await fetch('/api/tuner/scan/stop', { method: 'POST' });
      const data = await res.json();
      showToast(data.message);
    }

    async function probeOpcode() {
      const op = document.getElementById('probeOpcodeInput').value;
      showToast('Sende Opcode ' + op + ' …');
      const res = await fetch('/api/probe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ opcode: op })
      });
      const data = await res.json();
      document.getElementById('probeResult').innerText = data.success ? 
        'Antwort auf ' + data.opcode + ': ' + data.response : 'Fehler: ' + data.message;
    }

    async function analyzePcap() {
      const path = document.getElementById('pcapPathInput').value.trim();
      showToast('Analysiere PCAP…');
      const res = await fetch('/api/pcap/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ path })
      });
      const data = await res.json();
      document.getElementById('pcapResult').innerText = JSON.stringify(data.result || data.message, null, 2);
    }

    // Init
    window.addEventListener('DOMContentLoaded', () => {
      loadChannels();
      pollStatus();
      pollInterval = setInterval(pollStatus, 2500);
    });
  </script>
</body>
</html>
"""


async def index(request: Request) -> HTMLResponse:
    """Liefert die Hauptseite der Benutzeroberfläche aus."""
    return HTMLResponse(_HTML_PAGE)


# ---------------------------------------------------------------------------
# Starlette Application Routing
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
    Route("/api/stream/{prog_idx}", endpoint=api_stream_video, methods=["GET"]),
    Route("/api/stream/stop", endpoint=api_stream_stop, methods=["POST"]),
    Route("/api/record/start", endpoint=api_record_start, methods=["POST"]),
    Route("/api/record/stop", endpoint=api_record_stop, methods=["POST"]),
    Route("/api/recordings", endpoint=api_recordings_list, methods=["GET"]),
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
    import webbrowser

    if dongle_ip:
        manager.ip = dongle_ip

    display_host = "localhost" if host in ("0.0.0.0", "") else host
    url = f"http://{display_host}:{port}"
    print("\n" + "=" * 64)
    print(f"  WISI OR S2D – DVB-over-IP Web Control Center")
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
