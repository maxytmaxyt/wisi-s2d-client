"""
scheduler.py – Aufnahme- und Timer-Verwaltung für den WISI Web-Server
====================================================================
Verwaltet programmierte TV-Aufnahmen, den Hintergrund-Scheduler-Thread
sowie das Schreiben und Löschen von .ts-Aufnahmedateien.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from .streamer import DongleManager

log = logging.getLogger("wisi.ui.scheduler")

RECORDINGS_DIR = Path("recordings")
TIMERS_FILE = RECORDINGS_DIR / "timers.json"


@dataclass
class TimerEntry:
    """Repräsentiert eine programmierte TV-Aufnahme."""
    id: str
    prog_idx: int
    channel_name: str
    title: str
    start_time: float      # Unix-Timestamp
    duration_minutes: int
    status: str            # "scheduled", "recording", "completed", "failed", "cancelled", "expired"
    filename: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prog_idx": self.prog_idx,
            "channel_name": self.channel_name,
            "title": self.title,
            "start_time": self.start_time,
            "start_str": time.strftime("%Y-%m-%d %H:%M", time.localtime(self.start_time)),
            "duration_minutes": self.duration_minutes,
            "status": self.status,
            "filename": self.filename,
        }


class RecordingScheduler:
    """Verwaltet manuelle und zeitgesteuerte Aufnahmen."""

    def __init__(self, manager: DongleManager) -> None:
        self.manager = manager
        self._rec_lock = threading.RLock()
        self.recording_active: bool = False
        self.recording_path: Path | None = None
        self.recording_file: Any = None
        self.recording_start_time: float = 0.0
        self.recording_bytes: int = 0

        self.timers: list[TimerEntry] = []
        self.timers_lock = threading.RLock()
        self.active_timer_id: str | None = None
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None

        self._load_timers()
        self._start_scheduler()

    def _load_timers(self) -> None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        if not TIMERS_FILE.is_file():
            return
        try:
            data = json.loads(TIMERS_FILE.read_text(encoding="utf-8"))
            changed = False
            now = time.time()
            with self.timers_lock:
                self.timers = []
                for item in data:
                    status = item.get("status", "scheduled")
                    start_t = float(item["start_time"])
                    dur_m = int(item["duration_minutes"])
                    if status == "recording":
                        status = "completed" if now >= start_t + dur_m * 60 else "failed"
                        changed = True
                    self.timers.append(TimerEntry(
                        id=item["id"],
                        prog_idx=item["prog_idx"],
                        channel_name=item.get("channel_name", ""),
                        title=item.get("title", "Aufnahme"),
                        start_time=start_t,
                        duration_minutes=dur_m,
                        status=status,
                        filename=item.get("filename", ""),
                    ))
            if changed:
                self._save_timers()
            log.info("%d Timer aus %s geladen.", len(self.timers), TIMERS_FILE)
        except Exception as e:
            log.warning("Konnte Timer nicht laden: %s", e)

    def _save_timers(self) -> None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with self.timers_lock:
                data = [t.to_dict() for t in self.timers]
            TIMERS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        except Exception as e:
            log.error("Konnte Timer nicht speichern: %s", e)

    def _start_scheduler(self) -> None:
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            return
        self._scheduler_stop.clear()
        self._scheduler_thread = threading.Thread(target=self._scheduler_worker, daemon=True)
        self._scheduler_thread.start()

    def _scheduler_worker(self) -> None:
        while not self._scheduler_stop.is_set():
            now = time.time()
            with self.timers_lock:
                if self.active_timer_id:
                    active = next((t for t in self.timers if t.id == self.active_timer_id), None)
                    if active:
                        end_t = active.start_time + (active.duration_minutes * 60)
                        if now >= end_t:
                            log.info("Geplanter Timer beendet: %s", active.title)
                            self.stop_recording()
                            active.status = "completed"
                            self.active_timer_id = None
                            self._save_timers()
                    else:
                        self.active_timer_id = None

                if not self.active_timer_id:
                    for timer in self.timers:
                        if timer.status != "scheduled":
                            continue
                        end_t = timer.start_time + (timer.duration_minutes * 60)
                        if timer.start_time <= now < end_t:
                            log.info("Starte geplanten Timer: %s (%s)", timer.title, timer.channel_name)
                            if not timer.filename:
                                safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in timer.title)
                                safe_ch = "".join(c if c.isalnum() or c in " -_" else "_" for c in timer.channel_name)
                                timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(timer.start_time))
                                timer.filename = f"{safe_ch}_{safe_title}_{timestamp}.ts"

                            ok, msg = self.start_recording(timer.prog_idx, filename=timer.filename)
                            if ok:
                                timer.status = "recording"
                                self.active_timer_id = timer.id
                            else:
                                timer.status = "failed"
                                log.error("Timer-Start fehlgeschlagen: %s", msg)
                            self._save_timers()
                            break
                        elif now >= end_t:
                            timer.status = "expired"
                            self._save_timers()

            self._scheduler_stop.wait(2.0)

    def write_chunk(self, chunk: bytes) -> None:
        """Wird aus dem Streamer-Worker aufgerufen, wenn Aufnahme aktiv ist."""
        with self._rec_lock:
            if self.recording_active and self.recording_file:
                try:
                    self.recording_file.write(chunk)
                    self.recording_bytes += len(chunk)
                except Exception as rec_err:
                    log.error("Aufnahmefehler: %s", rec_err)

    def start_recording(self, prog_idx: int | None = None, filename: str | None = None) -> tuple[bool, str]:
        with self._rec_lock:
            if self.recording_active:
                return False, "Es läuft bereits eine Aufnahme"

            if prog_idx and (not self.manager.active_service or self.manager.active_service.prog_idx != prog_idx):
                if not self.manager.start_stream(prog_idx):
                    return False, "Konnte Stream für Aufnahme nicht starten (Dongle nicht erreichbar)"
                time.sleep(0.5)

            if not self.manager.active_service:
                return False, "Kein aktiver Kanal zum Aufnehmen"

            RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
            if not filename:
                safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.manager.active_service.name)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                safe_filename = f"{safe_name}_{timestamp}.ts"
            else:
                safe_filename = os.path.basename(filename)
                if not safe_filename:
                    return False, "Ungültiger Dateiname"

            rec_path = RECORDINGS_DIR / safe_filename
            try:
                self.recording_file = open(rec_path, "wb")  # noqa: SIM115
                self.recording_path = rec_path
                self.recording_active = True
                self.recording_start_time = time.time()
                self.recording_bytes = 0
                log.info("Aufnahme gestartet: %s", rec_path)
                return True, f"Aufnahme gestartet: {safe_filename}"
            except OSError as e:
                return False, f"Konnte Datei nicht öffnen: {e}"

    def stop_recording(self) -> tuple[bool, str]:
        with self._rec_lock:
            if not self.recording_active:
                return False, "Keine Aufnahme aktiv"

            self.recording_active = False
            path = self.recording_path
            if self.recording_file:
                try:
                    self.recording_file.flush()
                    self.recording_file.close()
                except Exception:
                    pass
                self.recording_file = None

            dur = time.time() - self.recording_start_time
            mb = self.recording_bytes / 1_048_576
            msg = f"Aufnahme beendet: {path.name if path else ''} ({mb:.1f} MB in {dur:.0f} s)"
            log.info(msg)
            return True, msg

    def list_recordings(self) -> list[dict[str, Any]]:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        files: list[dict[str, Any]] = []
        all_recs = list(RECORDINGS_DIR.glob("*.ts")) + list(RECORDINGS_DIR.glob("*.mp4"))
        for p in all_recs:
            if p.name.startswith("_timeshift"):
                continue
            stat = p.stat()
            files.append({
                "filename": p.name,
                "is_mp4": p.suffix.lower() == ".mp4",
                "size_mb": round(stat.st_size / 1_048_576, 2),
                "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "path": str(p.resolve()),
            })
        files.sort(key=lambda x: str(x["created"]), reverse=True)
        return files

    def delete_recording(self, filename: str) -> tuple[bool, str]:
        safe_name = os.path.basename(filename)
        path = RECORDINGS_DIR / safe_name
        if not path.is_file():
            return False, f"Datei nicht gefunden: {safe_name}"
        try:
            path.unlink()
            log.info("Aufnahme gelöscht: %s", safe_name)
            return True, f"Aufnahme gelöscht: {safe_name}"
        except OSError as e:
            return False, f"Fehler beim Löschen: {e}"

    def add_timer(
        self,
        prog_idx: int,
        title: str = "",
        start_time: float = 0.0,
        duration_minutes: int = 60,
    ) -> tuple[bool, str, TimerEntry | None]:
        if start_time <= 0:
            start_time = time.time()
        if duration_minutes <= 0:
            duration_minutes = 60

        ch_name = "Unbekannt"
        for ch in self.manager.channels:
            if ch.prog_idx == prog_idx:
                ch_name = ch.name
                break
        if ch_name == "Unbekannt":
            for svc in self.manager.services:
                if svc.prog_idx == prog_idx:
                    ch_name = svc.name
                    break

        if not title:
            title = f"{ch_name} Sendung"

        timer_id = str(uuid.uuid4())[:8]
        entry = TimerEntry(
            id=timer_id,
            prog_idx=prog_idx,
            channel_name=ch_name,
            title=title,
            start_time=start_time,
            duration_minutes=duration_minutes,
            status="scheduled",
        )
        with self.timers_lock:
            self.timers.append(entry)
            self._save_timers()

        log.info("Timer hinzugefügt: %s (%s, Start: %s, %d Min)", title, ch_name, entry.to_dict()["start_str"], duration_minutes)
        return True, f"Timer '{title}' auf {ch_name} erfolgreich programmiert.", entry

    def delete_timer(self, timer_id: str) -> tuple[bool, str]:
        with self.timers_lock:
            target = next((t for t in self.timers if t.id == timer_id), None)
            if not target:
                return False, f"Timer mit ID {timer_id} nicht gefunden"

            if self.active_timer_id == timer_id:
                self.stop_recording()
                self.active_timer_id = None

            self.timers.remove(target)
            self._save_timers()
        return True, f"Timer '{target.title}' gelöscht."

    def list_timers(self) -> list[dict[str, Any]]:
        with self.timers_lock:
            res = [t.to_dict() for t in self.timers]
        res.sort(key=lambda x: x["start_time"])
        return res
