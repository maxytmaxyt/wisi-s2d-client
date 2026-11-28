"""
api_stream.py – REST-Endpunkte für Status, Sender, EPG, Streaming und Diagnose
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
import queue
import time

from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

from ..cli import discovery
from ..core.models import Channel
from ..protocol import protocol
from ..tools.pcap_parser import analyze as pcap_analyze
from .state import manager
from .transcoder import find_ffmpeg, transcoded_stream_generator


async def api_status(request: Request) -> JSONResponse:
    """Liefert aktuellen Verbindungs-, Signal- und Streaming-Status."""
    return JSONResponse({
        "connected": manager.is_connected(),
        "ip": manager.ip,
        "ffmpeg_available": find_ffmpeg() is not None,
        "signal": {
            "locked": manager.signal_locked,
            "strength": manager.signal_strength,
            "quality": manager.signal_quality,
        },
        "streaming": dict(manager.stream_stats),
        "recording": {
            "active": manager.recording_active,
            "path": str(manager.recording_path.name) if manager.recording_path else "",
            "bytes": manager.recording_bytes,
            "seconds": round(time.time() - manager.recording_start_time, 1) if manager.recording_active else 0,
        },
        "scan": dict(manager.scan_status),
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
    """Sucht den WISI Dongle im Netzwerk über bestätigte APIX TCP-Prüfung."""
    results = await asyncio.to_thread(discovery.discover_dongles, manager.ip)
    return JSONResponse({"success": True, "devices": results})


async def api_info(request: Request) -> JSONResponse:
    """Liefert Hardware-, Firmware- und Session-Informationen."""
    info = await asyncio.to_thread(manager.get_dongle_info)
    return JSONResponse({"success": True, "info": info})


async def api_channels(request: Request) -> JSONResponse:
    """Gibt die Liste der Sender zurück (angereichert mit EPG-Daten)."""
    if not manager.channels and manager.tcp_sock:
        await asyncio.to_thread(manager.refresh_channels)
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


async def api_stream_video(request: Request) -> Response:
    """HTTP Live MPEG-TS Stream: Entschlüsselt TS-Pakete in Echtzeit und streamt sie an den Browser/VLC."""
    prog_idx_str = request.path_params.get("prog_idx")
    try:
        prog_idx = int(prog_idx_str, 0)
    except (ValueError, TypeError):
        return Response("Ungültiger prog_idx", status_code=400)

    if not (manager.active_service and manager.active_service.prog_idx == prog_idx and manager.stream_thread and manager.stream_thread.is_alive()):
        ok = await asyncio.to_thread(manager.start_stream, prog_idx)
        if not ok:
            return Response("Konnte Stream nicht starten (Dongle nicht erreichbar)", status_code=502)

    client_q = manager.subscribe_client()

    ffmpeg_bin = find_ffmpeg()
    raw_param = request.query_params.get("raw", "0")
    transcode_param = request.query_params.get("transcode", "auto")
    svc_name = manager.active_service.name if manager.active_service else ""
    is_hd = "HD" in svc_name.upper()

    need_transcode = bool(
        ffmpeg_bin and raw_param != "1" and
        (transcode_param == "1" or (transcode_param == "auto" and not is_hd))
    )

    if need_transcode and ffmpeg_bin:
        async def trans_gen() -> AsyncIterator[bytes]:
            try:
                async for chunk in transcoded_stream_generator(client_q, ffmpeg_bin, request.is_disconnected):
                    yield chunk
            finally:
                manager.unsubscribe_client(client_q)
        output_gen = trans_gen()
    else:
        async def stream_generator() -> AsyncIterator[bytes]:
            try:
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        chunk = await asyncio.to_thread(client_q.get, timeout=0.5)
                        if not chunk:
                            break
                        yield chunk
                    except queue.Empty:
                        continue
            finally:
                manager.unsubscribe_client(client_q)
        output_gen = stream_generator()

    return StreamingResponse(
        output_gen,
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


async def api_playlist_m3u(request: Request) -> Response:
    """Generiert eine vollständige M3U-Playlist für VLC, Kodi, Apple TV etc."""
    base_url = str(request.base_url)
    m3u_text = manager.generate_m3u(base_url)
    return Response(
        m3u_text,
        media_type="application/x-mpegurl",
        headers={"Content-Disposition": 'attachment; filename="wisi_channels.m3u"'},
    )


async def api_probe(request: Request) -> JSONResponse:
    """Sendet einen APIX-Opcode an den Dongle zur Diagnose."""
    try:
        body = await request.json()
        opcode = int(str(body.get("opcode", "0")), 0)
    except Exception:
        return JSONResponse({"success": False, "message": "Ungültiger Opcode"}, status_code=400)
    if not (0x04 <= opcode <= 0x1F):
        return JSONResponse({"success": False, "message": "Opcode 0x04-0x1F"}, status_code=400)

    def _do_probe():
        sock = manager.tcp_sock or protocol.connect(manager.ip)
        if not sock:
            raise ConnectionError("Verbindung fehlgeschlagen")
        try:
            with manager.lock:
                resp = protocol.send_recv(sock, protocol.cmd_probe(opcode), 4, f"probe 0x{opcode:02X}")
            return resp.hex(" ")
        finally:
            if not manager.tcp_sock:
                protocol.disconnect(sock)

    try:
        hex_res = await asyncio.to_thread(_do_probe)
        return JSONResponse({"success": True, "opcode": f"0x{opcode:02X}", "response": hex_res or "(keine Daten)"})
    except Exception as e:
        return JSONResponse({"success": False, "message": str(e)}, status_code=500)


async def api_pcap_analyze(request: Request) -> JSONResponse:
    """Analysiert eine PCAP-Datei auf APIX-Befehle."""
    try:
        body = await request.json()
        p = Path(body.get("path", ""))
        if not p.is_file():
            return JSONResponse({"success": False, "message": "PCAP nicht gefunden"}, status_code=404)
        res = await asyncio.to_thread(pcap_analyze, p)
        return JSONResponse({"success": True, "result": res})
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Analyse-Fehler: {e}"}, status_code=500)
