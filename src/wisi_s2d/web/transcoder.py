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
    if os.name == "nt":
        candidates = [
            Path("ffmpeg.exe"),
            Path(__file__).resolve().parents[3] / "ffmpeg.exe",
        ]
        for c in candidates:
            if c.is_file():
                return str(c.resolve())

        # Falls komprimiertes FFmpeg-Zip unter Windows vorhanden ist, automatisch entpacken
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

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass

    return None


def is_ffmpeg_available() -> bool:
    return find_ffmpeg() is not None


_vaapi_checked = False
_vaapi_device: str | None = None


def find_vaapi_device(ffmpeg_path: str | None = None) -> str | None:
    """Prüft, ob eine Linux VA-API GPU (z. B. Intel Cherry Trail / Wyse 3040) für h264_vaapi nutzbar ist."""
    global _vaapi_checked, _vaapi_device
    if _vaapi_checked:
        return _vaapi_device
    _vaapi_checked = True

    if os.name == "nt":
        return None
    dri_dir = Path("/dev/dri")
    if not dri_dir.is_dir():
        return None

    exe = ffmpeg_path or find_ffmpeg()
    if not exe:
        return None

    for dev in sorted(dri_dir.glob("renderD*")):
        try:
            res = subprocess.run(
                [
                    exe,
                    "-hide_banner",
                    "-loglevel", "error",
                    "-vaapi_device", str(dev),
                    "-f", "lavfi",
                    "-i", "color=c=black:s=64x64:d=0.1",
                    "-vf", "format=nv12,hwupload",
                    "-c:v", "h264_vaapi",
                    "-f", "null",
                    "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=3.0,
                check=False,
            )
            if res.returncode == 0:
                log.info("Hardware-Transkodierung aktiviert (VA-API: %s)", dev)
                _vaapi_device = str(dev)
                return _vaapi_device
        except Exception as exc:
            log.debug("VA-API-Test für %s fehlgeschlagen: %s", dev, exc)
    return None


def _lower_process_priority(proc: subprocess.Popen[bytes], niceness: int = 5) -> None:
    """Senkt die CPU-Priorität von FFmpeg auf POSIX, damit Live-UDP-Empfang stets Vorrang hat."""
    if os.name == "nt":
        return
    try:
        os.setpriority(os.PRIO_PROCESS, proc.pid, niceness)
    except OSError:
        pass


def start_ffmpeg_process(ffmpeg_path: str) -> subprocess.Popen[bytes]:
    """Startet FFmpeg mit optimaler CPU/GPU-Aufteilung (GPU: H.264-Encode, CPU: Audio/Demux)."""
    vaapi_dev = find_vaapi_device(ffmpeg_path)
    if vaapi_dev:
        # Hybrid-Split: CPU macht Demux + MPEG2-Decode + AAC-Audio (max. 2 Threads),
        # Intel-GPU (VA-API) übernimmt das rechenintensive H.264-Encoding.
        cmd = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-fflags", "+nobuffer+flush_packets",
            "-threads", "2",
            "-vaapi_device", vaapi_dev,
            "-i", "pipe:0",
            "-vf", "format=nv12,hwupload",
            "-c:v", "h264_vaapi",
            "-qp", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-f", "mpegts",
            "pipe:1",
        ]
    else:
        # Reiner CPU-Fallback: mind. 1 Kern für UDP-Stream, AES-Entschlüsselung & Webserver freihalten
        cpu_count = os.cpu_count() or 2
        ff_threads = str(max(1, cpu_count - 1))
        cmd = [
            ffmpeg_path,
            "-hide_banner",
            "-loglevel", "error",
            "-fflags", "+nobuffer+flush_packets",
            "-i", "pipe:0",
            "-threads", ff_threads,
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
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
        creationflags=creationflags,
    )
    _lower_process_priority(proc, 5)
    return proc


async def transcoded_stream_generator(
    client_q: queue.Queue[bytes],
    ffmpeg_path: str,
    is_disconnected_fn,
) -> AsyncIterator[bytes]:
    """Liest Roh-TS aus client_q, leitet durch FFmpeg und yieldet H.264-Pakete."""
    proc = start_ffmpeg_process(ffmpeg_path)
    stop_event = threading.Event()

    def _feeder() -> None:
        stdin = proc.stdin
        if stdin is None:
            return
        try:
            while not stop_event.is_set():
                try:
                    chunk = client_q.get(timeout=0.4)
                    if not chunk:
                        break
                    stdin.write(chunk)
                    stdin.flush()
                except queue.Empty:
                    continue
                except (BrokenPipeError, OSError):
                    break
        except Exception as e:
            log.debug("Transcoder-Feeder beendet: %s", e)
        finally:
            try:
                stdin.close()
            except Exception:
                pass

    feed_thread = threading.Thread(target=_feeder, daemon=True)
    feed_thread.start()

    stdout = proc.stdout
    try:
        while stdout is not None:
            if await is_disconnected_fn():
                break
            chunk = await asyncio.to_thread(stdout.read, 32768)
            if not chunk:
                break
            yield chunk
    finally:
        stop_event.set()
        try:
            proc.kill()
            proc.wait(timeout=1.0)
        except Exception:
            pass
        feed_thread.join(timeout=0.5)
