"""
api_record.py – REST-Endpunkte für Aufnahmen, Timer-Planer und Tuner-Suchlauf
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import os
import subprocess
import time

from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response, StreamingResponse

from ..core.decrypt import decrypt_ts_file
from ..core.scan import SCAN_AUTO, SCAN_MANUAL, SCAN_NETWORK
from .state import manager
from .streamer import RECORDINGS_DIR
from .transcoder import _lower_process_priority, find_ffmpeg, find_vaapi_device


async def api_record_start(request: Request) -> JSONResponse:
    """Startet Aufnahme des aktuellen oder angegebenen Kanals."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    prog_idx = body.get("prog_idx")
    filename = body.get("filename")
    ok, msg = await asyncio.to_thread(manager.start_recording, prog_idx, filename)
    return JSONResponse({"success": ok, "message": msg}, status_code=200 if ok else 400)


async def api_record_stop(request: Request) -> JSONResponse:
    """Stoppt die laufende Aufnahme."""
    ok, msg = await asyncio.to_thread(manager.stop_recording)
    return JSONResponse({"success": ok, "message": msg})


async def api_timeshift_save(request: Request) -> JSONResponse:
    """Sichert den aktuellen Timeshift-Puffer als eigenständige Aufnahme."""
    ok, msg = await asyncio.to_thread(manager.engine.save_timeshift_as_recording)
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
        check=False,
    )
    is_mpeg2 = "mpeg2video" in (probe.stderr or "").lower()

    vaapi_dev = await asyncio.to_thread(find_vaapi_device, ffmpeg_bin) if is_mpeg2 else None
    cmd = [
        ffmpeg_bin,
        "-hide_banner",
        "-loglevel", "error",
    ]
    if is_mpeg2 and vaapi_dev:
        cmd.extend([
            "-threads", "2",
            "-vaapi_device", vaapi_dev,
            "-i", str(path),
            "-vf", "format=nv12,hwupload",
            "-c:v", "h264_vaapi",
            "-qp", "23",
        ])
    elif is_mpeg2:
        ff_threads = str(max(1, (os.cpu_count() or 2) - 1))
        cmd.extend([
            "-i", str(path),
            "-threads", ff_threads,
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency", "-crf", "23",
        ])
    else:
        cmd.extend(["-i", str(path), "-c:v", "copy"])
    cmd.extend([
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "pipe:1",
    ])

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = await asyncio.to_thread(
        subprocess.Popen,
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    _lower_process_priority(proc, 5)

    async def stream_mp4() -> AsyncIterator[bytes]:
        stdout = proc.stdout
        try:
            while stdout is not None:
                try:
                    if await request.is_disconnected():
                        break
                except Exception:
                    pass
                chunk = await asyncio.to_thread(stdout.read, 32768)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                proc.terminate()
                proc.wait(timeout=1.0)
            except Exception:
                try:
                    proc.kill()
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
    if path.suffix.lower() == ".mp4":
        return JSONResponse({"success": False, "message": "Datei liegt bereits im MP4-Format vor"}, status_code=400)

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
        res = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, check=False)
        if res.returncode != 0:
            vaapi_dev = find_vaapi_device(ffmpeg_bin)
            if vaapi_dev:
                cmd_reencode = [
                    ffmpeg_bin,
                    "-y",
                    "-vaapi_device", vaapi_dev,
                    "-i", str(path),
                    "-vf", "format=nv12,hwupload",
                    "-c:v", "h264_vaapi",
                    "-qp", "23",
                    "-c:a", "aac",
                    "-b:a", "128k",
                    "-movflags", "+faststart",
                    str(out_path),
                ]
            else:
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
            res = subprocess.run(cmd_reencode, stderr=subprocess.PIPE, text=True, check=False)
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
    """Entschlüsselt eine ausgewählte .ts-Datei (AES-128-ECB) im Aufnahme-Verzeichnis."""
    try:
        body = await request.json()
        input_file = body.get("filename") or body.get("path")
    except Exception:
        input_file = None

    if not input_file:
        return JSONResponse({"success": False, "message": "Keine Datei angegeben"}, status_code=400)

    safe_name = os.path.basename(str(input_file))
    target_path = RECORDINGS_DIR / safe_name
    if not target_path.is_file():
        return JSONResponse({"success": False, "message": f"Datei nicht gefunden: {safe_name}"}, status_code=404)

    t0 = time.perf_counter()
    try:
        out_path = await asyncio.to_thread(decrypt_ts_file, target_path)
        dt = time.perf_counter() - t0
        size_mb = out_path.stat().st_size / 1_048_576
        return JSONResponse({
            "success": True,
            "message": f"Erfolgreich entschlüsselt: {out_path.name} ({size_mb:.2f} MB in {dt:.2f}s = {size_mb / max(dt, 0.001):.1f} MB/s)",
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
        title = str(body.get("title", "")).strip()
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
    return JSONResponse({"success": ok, "message": msg}, status_code=200 if ok else 404)


async def api_tuner_tune(request: Request) -> JSONResponse:
    """Stellt den Tuner auf einen Transponder ein."""
    try:
        body = await request.json()
        freq = int(body.get("freq", 11362))
        sr = int(body.get("sym", 22000))
        pol = str(body.get("pol", "H")).strip().upper()
        sat_lon = int(body.get("sat_lon", 192))
    except Exception as e:
        return JSONResponse({"success": False, "message": f"Ungültige Parameter: {e}"}, status_code=400)

    ok, msg = await asyncio.to_thread(manager.tune_transponder, freq, sr, pol, sat_lon)
    return JSONResponse({"success": ok, "message": msg})


async def api_tuner_scan_start(request: Request) -> JSONResponse:
    """Startet den DVB-S2 Sendersuchlauf."""
    try:
        body = await request.json()
        mode_val = int(body.get("scan_type", body.get("mode", SCAN_MANUAL)))
        filter_val = int(body.get("search_range", body.get("filter", 0)))
        network_scan = body.get("network_scan")
    except Exception:
        mode_val = SCAN_MANUAL
        filter_val = 0
        network_scan = None

    mode_map = {0: SCAN_MANUAL, 1: SCAN_AUTO, 2: SCAN_NETWORK}
    scan_mode = mode_map.get(mode_val, SCAN_MANUAL)
    is_net = bool(network_scan) if network_scan is not None else (scan_mode == SCAN_NETWORK)
    ok, msg = await asyncio.to_thread(
        manager.start_scan,
        scan_type=scan_mode,
        network_scan=is_net,
        search_range=filter_val,
    )
    return JSONResponse({"success": ok, "message": msg})


async def api_tuner_scan_stop(request: Request) -> JSONResponse:
    """Bricht den laufenden Sendersuchlauf ab."""
    ok, msg = await asyncio.to_thread(manager.stop_scan)
    return JSONResponse({"success": ok, "message": msg})
