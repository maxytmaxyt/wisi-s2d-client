"""
transcoder.py – Echtzeit-Transkodierung von MPEG-2 SD nach H.264 per FFmpeg
===========================================================================
Wandelt MPEG-2 Video & MP2 Audio für HTML5-Browser (MSE / mpegts.js) in
H.264 (AVC) + AAC um (Preset ultrafast, zero latency).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import logging
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading

log = logging.getLogger("wisi.transcoder")


def find_ffmpeg() -> str | None:
    """Findet ein verfügbares FFmpeg-Binary."""
    candidates = [
        Path("ffmpeg.exe"),
        Path(__file__).resolve().parents[3] / "ffmpeg.exe",
    ]
    for c in candidates:
        if c.is_file():
            return str(c.resolve())

    # Falls komprimiertes FFmpeg-Zip vorhanden ist, automatisch entpacken
    zip_candidates = [
        Path("ffmpeg-exe.zip"),
        Path(__file__).resolve().parents[3] / "ffmpeg-exe.zip",
    ]
    for z in zip_candidates:
        if z.is_file():
            try:
                import zipfile
                target_dir = z.parent
                with zipfile.ZipFile(z, "r") as zf:
                    zf.extractall(target_dir)
                exe = target_dir / "ffmpeg.exe"
                if exe.is_file():
                    return str(exe.resolve())
            except Exception as e:
                log.warning("Konnte %s nicht entpacken: %s", z, e)

    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass

    return shutil.which("ffmpeg")


def is_ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


def start_ffmpeg_process(ffmpeg_path: str) -> subprocess.Popen:
    """Startet FFmpeg mit minimaler Latenz und Pipe-Ein/Ausgabe."""
    cmd = [
        ffmpeg_path,
        "-hide_banner",
        "-loglevel", "error",
        "-fflags", "+nobuffer+flush_packets",
        "-i", "pipe:0",
        "-threads", "0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "mpegts",
        "pipe:1",
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NO_WINDOW

    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
        creationflags=creationflags,
    )


async def transcoded_stream_generator(
    client_q: queue.Queue,
    ffmpeg_path: str,
    is_disconnected_fn,
) -> AsyncIterator[bytes]:
    """Liest Roh-TS aus client_q, leitet durch FFmpeg und yieldet H.264-Pakete."""
    proc = start_ffmpeg_process(ffmpeg_path)
    stop_event = threading.Event()

    def _feeder():
        try:
            while not stop_event.is_set():
                try:
                    chunk = client_q.get(timeout=0.4)
                    if not chunk:
                        break
                    proc.stdin.write(chunk)
                    proc.stdin.flush()
                except queue.Empty:
                    continue
                except (BrokenPipeError, OSError):
                    break
        except Exception as e:
            log.debug("Transcoder-Feeder beendet: %s", e)
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass

    feed_thread = threading.Thread(target=_feeder, daemon=True)
    feed_thread.start()

    try:
        while True:
            if await is_disconnected_fn():
                break
            chunk = await asyncio.to_thread(proc.stdout.read, 32768)
            if not chunk:
                break
            yield chunk
    finally:
        stop_event.set()
        try:
            proc.kill()
        except Exception:
            pass
        feed_thread.join(timeout=0.5)
