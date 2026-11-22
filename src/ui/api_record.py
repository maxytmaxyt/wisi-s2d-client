"""
api_record.py – REST-Endpunkte für Aufnahmen, Timer-Planer und Tuner-Suchlauf
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
from pathlib import Path
import subprocess
import time

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from decrypt import decrypt_ts_file
from scan import SCAN_AUTO, SCAN_MANUAL, SCAN_NETWORK
from ui.state import manager
from ui.streamer import RECORDINGS_DIR
from ui.transcoder import find_ffmpeg


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
    filename = request.path_params.get("filename", "")
    safe_name = os.path.basename(filename)
    path = RECORDINGS_DIR / safe_name
    if not path.is_file():
        return Response("Datei nicht gefunden", status_code=404)
    media_type = "video/mp4" if safe_name.lower().endswith(".mp4") else "video/mp2t"
    return FileResponse(
        str(path),
        media_type=media_type,
        filename=safe_name,
    )


async def api_recording_stream(request: Request) -> Response:
    """Streamt eine Aufnahme als HTML5-kompatibles Fragmented-MP4 (H.264+AAC)."""
    filename = request.path_params.get("filename", "")
    safe_name = os.path.basename(filename)
    path = RECORDINGS_DIR / safe_name
    if not path.is_file():
        return Response("Datei nicht gefunden", status_code=404)

    if safe_name.lower().endswith(".mp4"):
        return FileResponse(str(path), media_type="video/mp4")

    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        return FileResponse(str(path), media_type="video/mp2t")

    probe = await asyncio.to_thread(
        subprocess.run,
        [ffmpeg_bin, "-i", str(path)],
        stderr=subprocess.PIPE,
        text=True,
    )
    is_mpeg2 = "mpeg2video" in probe.stderr.lower()

    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
        "-i", str(path),
    ]
    if is_mpeg2:
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "23"])
    else:
        cmd.extend(["-c:v", "copy"])
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ])

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )

    async def stream_mp4() -> AsyncIterator[bytes]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                chunk = await asyncio.to_thread(proc.stdout.read, 32768)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                pass

    return StreamingResponse(
        stream_mp4(),
        media_type="video/mp4",
        headers={
            "Cache-Control": "no-cache",
            "Accept-Ranges": "none",
        },
    )


async def api_recordings_convert(request: Request) -> JSONResponse:
    """Wandelt eine .ts-Aufnahme in ein standardisiertes .mp4 um."""
    try:
        body = await request.json()
        filename = body.get("filename", "")
    except Exception:
        filename = ""

    safe_name = os.path.basename(filename)
    path = RECORDINGS_DIR / safe_name
    if not path.is_file():
        return JSONResponse({"success": False, "message": "Datei nicht gefunden"}, status_code=404)

    ffmpeg_bin = find_ffmpeg()
    if not ffmpeg_bin:
        return JSONResponse({"success": False, "message": "FFmpeg nicht verfügbar"}, status_code=500)

    out_name = f"{path.stem}.mp4"
    out_path = RECORDINGS_DIR / out_name

    def _convert() -> tuple[bool, str]:
        cmd = [
            ffmpeg_bin,
            "-y",
            "-i", str(path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            "-movflags", "+faststart",
            str(out_path),
        ]
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            cmd_reencode = [
                ffmpeg_bin,
                "-y",
                "-i", str(path),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(out_path),
            ]
            res = subprocess.run(cmd_reencode, stderr=subprocess.PIPE, text=True)
        return (res.returncode == 0, out_name)

    ok, res_name = await asyncio.to_thread(_convert)
    if ok:
        return JSONResponse({
            "success": True,
            "message": f"Aufnahme erfolgreich als MP4 gespeichert: {res_name}",
            "filename": res_name,
        })
    return JSONResponse({"success": False, "message": "Konvertierung fehlgeschlagen"}, status_code=500)


async def api_recording_delete(request: Request) -> JSONResponse:
    """Löscht eine gespeicherte Aufnahme."""
    filename = request.path_params.get("filename", "")
    ok, msg = await asyncio.to_thread(manager.delete_recording, filename)
    return JSONResponse({"success": ok, "message": msg}, status_code=200 if ok else 404)


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
        mode_val = int(body.get("mode", 0))
        filter_val = int(body.get("filter", 0))
    except Exception:
        mode_val = 0
        filter_val = 0

    mode_map = {0: SCAN_MANUAL, 1: SCAN_AUTO, 2: SCAN_NETWORK}
    scan_mode = mode_map.get(mode_val, SCAN_MANUAL)
    ok, msg = await asyncio.to_thread(manager.start_scan, scan_type=scan_mode, search_range=filter_val)
    return JSONResponse({"success": ok, "message": msg})


async def api_tuner_scan_stop(request: Request) -> JSONResponse:
    """Bricht den laufenden Sendersuchlauf ab."""
    ok, msg = await asyncio.to_thread(manager.stop_scan)
    return JSONResponse({"success": ok, "message": msg})
