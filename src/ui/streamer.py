"""
streamer.py – Hintergrund-Streaming-Engine und Gerätesteuerung für die WISI Web-UI
==================================================================================
DongleManager – Verwaltet TCP/UDP-Verbindungen, Senderliste, EPG, Tuner-Suchlauf,
                Live-Streaming über HTTP (für Browser-Player & VLC) und Aufnahmen.
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import asdict, dataclass
import json
import logging
import os
from pathlib import Path
import queue
import socket
import threading
import time
import uuid

from channels import channels_to_services, fetch_channel_list
from decrypt import decrypt_ts_file, descramble_ts_block
from keepalive import _keepalive_worker
from models import FALLBACK_SERVICE, Channel, ServiceEntry
import protocol
from scan import (
    DVBS2_TUNER_TYPE,
    SCAN_AUTO,
    SCAN_MANUAL,
    SCAN_NETWORK,
    SCAN_STOP,
    cmd_dvbs2_diseqc_set,
    cmd_dvbs2_lnb_set,
    cmd_dvbs2_satellite_set,
    cmd_dvbs2_tuner_set,
    cmd_scan_result_data,
    cmd_scan_result_size,
    cmd_scan_start_stop,
    fetch_dongle_info,
    parse_tuner_scan_status,
)
from stream import prepare_channel, stream
import wisi.discovery as discovery
import wisi.epg as epg_module

log = logging.getLogger("wisi.ui.streamer")

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

    def to_dict(self) -> dict[str, object]:
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


class DongleManager:
    """Zentrale Steuerungs- und Streaming-Klasse für die Web-Oberfläche."""

    def __init__(self, default_ip: str = protocol.DEFAULT_IP):
        self.ip = default_ip
        self.tcp_sock: socket.socket | None = None
        self.lock = threading.Lock()
        self.keepalive_stop = threading.Event()
        self.keepalive_thread: threading.Thread | None = None

        self.channels: list[Channel] = []
        self.services: list[ServiceEntry] = []
        self.dongle_info: dict[str, object] = {
            "model_name": "WISI OR S2D",
            "tuner_type": 26,
            "tuner_name": "DVB-S2",
        }
        self.epg_data: dict[int, list[dict]] = {}

        # Signal-Monitoring
        self.signal_strength: int = 0
        self.signal_quality: int = 0
        self.signal_locked: bool = False
        self._signal_stop = threading.Event()
        self._signal_thread: threading.Thread | None = None

        # Aktiver Stream
        self.active_service: ServiceEntry | None = None
        self.stream_stop_event = threading.Event()
        self.stream_thread: threading.Thread | None = None
        self.stream_clients: list[queue.Queue[bytes]] = []
        self.stream_clients_lock = threading.Lock()
        self.stream_stats: dict[str, object] = {
            "is_streaming": False,
            "channel_name": "",
            "prog_idx": 0,
            "kbps": 0.0,
            "bytes": 0,
            "blocks": 0,
            "elapsed": 0.0,
        }

        # Aktive Aufnahme
        self.recording_active: bool = False
        self.recording_path: Path | None = None
        self.recording_file = None
        self.recording_start_time: float = 0.0
        self.recording_bytes: int = 0

        # Scan-Status
        self.scan_in_progress: bool = False
        self.scan_status: dict[str, object] = {
            "in_progress": False,
            "progress": 0,
            "lock": False,
            "agc": 0,
            "snr": 0,
            "freq": 0,
            "symbol_rate": 0,
            "tv_count": 0,
            "radio_count": 0,
        }
        self._scan_stop = threading.Event()
        self._scan_thread: threading.Thread | None = None

        # Lokale EPG-Datei vorladen falls vorhanden
        self._load_cached_epg()

        # Timer- & Aufnahme-Scheduler
        self.timers: list[TimerEntry] = []
        self.timers_lock = threading.RLock()
        self.active_timer_id: str | None = None
        self._scheduler_stop = threading.Event()
        self._scheduler_thread: threading.Thread | None = None
        self._load_timers()
        self._start_scheduler()

    def _load_cached_epg(self) -> None:
        epg_file = Path("epg.json")
        if epg_file.is_file():
            try:
                data = json.loads(epg_file.read_text(encoding="utf-8"))
                for ch in data.get("channels", []):
                    sid = ch.get("service_id")
                    events = ch.get("events", [])
                    if sid is not None and events:
                        self.epg_data[sid] = events
                # Falls noch keine Kanalliste geladen ist, aus epg.json initialisieren
                if not self.channels:
                    cached_channels: list[Channel] = []
                    for ch in data.get("channels", []):
                        cached_channels.append(Channel(
                            prog_idx=ch.get("prog_idx", 0),
                            service_id=ch.get("service_id", 0),
                            ts_id=1,
                            freq=11362,
                            pol="H",
                            sym=22000,
                            lcn=ch.get("pat_index", 0),
                            name=ch.get("name", "Unbekannt"),
                            fta=True,
                            ch_type="TV",
                        ))
                    if cached_channels:
                        self.channels = cached_channels
                        self.services = channels_to_services(cached_channels)
            except Exception as e:
                log.debug("Konnte epg.json nicht laden: %s", e)

    # -------------------------------------------------------------------------
    # Verbindung
    # -------------------------------------------------------------------------
    def is_connected(self) -> bool:
        return self.tcp_sock is not None

    def connect(self, ip: str | None = None) -> tuple[bool, str]:
        if ip:
            self.ip = ip.strip()

        with self.lock:
            if self.tcp_sock is not None:
                self._disconnect_internal()

            log.info("Verbinde mit WISI Dongle unter %s …", self.ip)
            sock = protocol.connect(self.ip)
            if sock is None:
                return False, f"TCP-Verbindung zu {self.ip}:8802 fehlgeschlagen"

            self.tcp_sock = sock
            self.keepalive_stop.clear()
            self.keepalive_thread = threading.Thread(
                target=_keepalive_worker,
                args=(self.tcp_sock, self.lock, self.keepalive_stop),
                daemon=True,
            )
            self.keepalive_thread.start()

            # Hardware-Informationen abrufen
            try:
                self.dongle_info = fetch_dongle_info(self.tcp_sock, self.lock)
            except Exception as exc:
                log.warning("Hardware-Info Abruf fehlgeschlagen: %s", exc)

        # Kanalliste laden
        self.refresh_channels()

        # Signal-Monitoring im Hintergrund starten
        self._signal_stop.clear()
        self._signal_thread = threading.Thread(target=self._signal_monitor_loop, daemon=True)
        self._signal_thread.start()

        return True, "Erfolgreich verbunden"

    def disconnect(self) -> None:
        with self.lock:
            self._disconnect_internal()

    def _disconnect_internal(self) -> None:
        self.stop_stream()
        self._signal_stop.set()
        if self.keepalive_thread is not None:
            self.keepalive_stop.set()
            self.keepalive_thread.join(timeout=2.0)
            self.keepalive_thread = None

        if self.tcp_sock is not None:
            protocol.disconnect(self.tcp_sock)
            self.tcp_sock = None

    def _signal_monitor_loop(self) -> None:
        while not self._signal_stop.wait(2.5):
            if not self.tcp_sock:
                break
            try:
                with self.lock:
                    r = protocol.send_recv(self.tcp_sock, protocol.cmd_signal(), 17, "0x02 signal")
                if len(r) >= 5:
                    self.signal_locked = bool(r[2] & 0x01)
                    self.signal_strength = r[3]
                    self.signal_quality = r[4]
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # Kanäle & EPG
    # -------------------------------------------------------------------------
    def refresh_channels(self) -> list[Channel]:
        if not self.tcp_sock:
            # Wenn offline, nutze bereits geladene oder Fallback
            if not self.services:
                self.services = [FALLBACK_SERVICE]
            return self.channels

        try:
            with self.lock:
                channels = fetch_channel_list(self.tcp_sock, self.lock)
            if channels:
                self.channels = channels
                self.services = channels_to_services(channels)
                log.info("%d Kanäle geladen", len(channels))
        except Exception as e:
            log.warning("Fehler beim Laden der Kanalliste: %s", e)
        return self.channels

    def refresh_epg(self, limit: int | None = None) -> dict[int, list[dict]]:
        if not self.tcp_sock or not self.services:
            return self.epg_data

        target_services = self.services[:limit] if limit else self.services
        stop_evt = threading.Event()
        try:
            epg_results = epg_module.enrich_with_epg(
                self.tcp_sock, self.lock, target_services, stop_evt
            )
            self.epg_data.update(epg_results)
            # Speichere aktualisiertes epg.json
            payload = {
                "device_ip": self.ip,
                "service_count": len(self.services),
                "services_with_epg": len(self.epg_data),
                "channels": [
                    {
                        "pat_index": svc.pat_index,
                        "service_id": svc.service_id,
                        "prog_idx": svc.prog_idx,
                        "name": svc.name,
                        "events": self.epg_data.get(svc.service_id, []),
                    }
                    for svc in self.services
                ],
            }
            Path("epg.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            log.warning("EPG-Aktualisierung fehlgeschlagen: %s", e)
        return self.epg_data

    # -------------------------------------------------------------------------
    # Streaming Engine
    # -------------------------------------------------------------------------
    def start_stream(self, prog_idx: int) -> bool:
        if not self.tcp_sock:
            # Versuche automatische Verbindung
            ok, _ = self.connect()
            if not ok:
                return False

        # Finde Dienst
        svc = next((s for s in self.services if s.prog_idx == prog_idx), None)
        if svc is None:
            # Fallback Dienst mit angegebenem prog_idx bauen
            svc = ServiceEntry(
                pat_index=0,
                prog_idx=prog_idx,
                service_id=0,
                name=f"Kanal 0x{prog_idx:08X}",
            )

        if self.active_service and self.active_service.prog_idx == prog_idx and self.stream_thread and self.stream_thread.is_alive():
            return True

        self.stop_stream()

        self.active_service = svc
        self.stream_stop_event.clear()
        self.stream_stats = {
            "is_streaming": True,
            "channel_name": svc.name,
            "prog_idx": svc.prog_idx,
            "kbps": 0.0,
            "bytes": 0,
            "blocks": 0,
            "elapsed": 0.0,
        }

        self.stream_thread = threading.Thread(
            target=self._run_stream_worker,
            args=(svc,),
            daemon=True,
        )
        self.stream_thread.start()
        return True

    def stop_stream(self) -> None:
        self.stream_stop_event.set()
        if self.stream_thread and self.stream_thread.is_alive():
            self.stream_thread.join(timeout=3.0)
            self.stream_thread = None

        self.active_service = None
        self.stream_stats["is_streaming"] = False

        if self.recording_active:
            self.stop_recording()

        # Alle wartenden Clients benachrichtigen
        with self.stream_clients_lock:
            for q in self.stream_clients:
                try:
                    q.put_nowait(b"")
                except Exception:
                    pass
            self.stream_clients.clear()

    def _run_stream_worker(self, svc: ServiceEntry) -> None:
        def on_chunk(chunk: bytes) -> None:
            # Sende an alle verbundenen HTTP-Clients
            with self.stream_clients_lock:
                for q in list(self.stream_clients):
                    try:
                        if q.qsize() > 50:  # Puffer-Limit: ca. 2.4 MB
                            try:
                                q.get_nowait()
                            except queue.Empty:
                                pass
                        q.put_nowait(chunk)
                    except Exception:
                        pass

            # Falls Aufnahme aktiv ist, in Datei schreiben
            if self.recording_active and self.recording_file:
                try:
                    self.recording_file.write(chunk)
                    self.recording_bytes += len(chunk)
                except Exception as rec_err:
                    log.error("Aufnahmefehler: %s", rec_err)

        def on_status(stats: dict[str, object]) -> None:
            self.stream_stats.update(stats)
            self.stream_stats["is_streaming"] = True

        try:
            stream(
                tcp_sock=self.tcp_sock,
                lock=self.lock,
                svc=svc,
                output_path="",
                duration_s=0.0,
                keepalive_active=True,
                decrypt_after=False,
                stop_event=self.stream_stop_event,
                chunk_callback=on_chunk,
                status_callback=on_status,
                live_decrypt=True,
            )
        except Exception as e:
            log.error("Streaming-Thread-Fehler: %s", e)
        finally:
            self.stream_stats["is_streaming"] = False

    def subscribe_client(self) -> queue.Queue[bytes]:
        q: queue.Queue[bytes] = queue.Queue(maxsize=100)
        with self.stream_clients_lock:
            self.stream_clients.append(q)
        return q

    def unsubscribe_client(self, q: queue.Queue[bytes]) -> None:
        with self.stream_clients_lock:
            if q in self.stream_clients:
                self.stream_clients.remove(q)

    # -------------------------------------------------------------------------
    # Aufnahmen
    # -------------------------------------------------------------------------
    def start_recording(self, prog_idx: int | None = None, filename: str | None = None) -> tuple[bool, str]:
        if prog_idx and (not self.active_service or self.active_service.prog_idx != prog_idx):
            self.start_stream(prog_idx)
            time.sleep(0.5)

        if not self.active_service:
            return False, "Kein aktiver Kanal zum Aufnehmen"

        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        if not filename:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in self.active_service.name)
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"{safe_name}_{timestamp}.ts"

        rec_path = RECORDINGS_DIR / filename
        try:
            self.recording_file = open(rec_path, "wb")
            self.recording_path = rec_path
            self.recording_active = True
            self.recording_start_time = time.time()
            self.recording_bytes = 0
            log.info("Aufnahme gestartet: %s", rec_path)
            return True, f"Aufnahme gestartet: {filename}"
        except OSError as e:
            return False, f"Konnte Datei nicht öffnen: {e}"

    def stop_recording(self) -> tuple[bool, str]:
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

    def list_recordings(self) -> list[dict[str, object]]:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        files = []
        for p in RECORDINGS_DIR.glob("*.ts"):
            stat = p.stat()
            files.append({
                "filename": p.name,
                "size_mb": round(stat.st_size / 1_048_576, 2),
                "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime)),
                "path": str(p.resolve()),
            })
        files.sort(key=lambda x: x["created"], reverse=True)
        return files

    def delete_recording(self, filename: str) -> tuple[bool, str]:
        """Löscht eine Aufnahme-Datei sicher aus recordings/."""
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

    # -------------------------------------------------------------------------
    # Timer & Aufnahme-Scheduler
    # -------------------------------------------------------------------------
    def _load_timers(self) -> None:
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        if not TIMERS_FILE.is_file():
            return
        try:
            data = json.loads(TIMERS_FILE.read_text(encoding="utf-8"))
            with self.timers_lock:
                self.timers = []
                for item in data:
                    self.timers.append(TimerEntry(
                        id=item["id"],
                        prog_idx=item["prog_idx"],
                        channel_name=item.get("channel_name", ""),
                        title=item.get("title", "Aufnahme"),
                        start_time=float(item["start_time"]),
                        duration_minutes=int(item["duration_minutes"]),
                        status=item.get("status", "scheduled"),
                        filename=item.get("filename", ""),
                    ))
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
                # 1. Aktiven Timer prüfen & beenden wenn Dauer abgelaufen
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

                # 2. Fällige Timer prüfen & starten
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

    def add_timer(
        self,
        prog_idx: int,
        title: str = "",
        start_time: float = 0.0,
        duration_minutes: int = 60,
    ) -> tuple[bool, str, TimerEntry | None]:
        """Fügt einen neuen Aufnahme-Timer hinzu."""
        if start_time <= 0:
            start_time = time.time()
        if duration_minutes <= 0:
            duration_minutes = 60

        # Kanalname ermitteln
        ch_name = "Unbekannt"
        for ch in self.channels:
            if ch.prog_idx == prog_idx:
                ch_name = ch.name
                break
        if ch_name == "Unbekannt":
            for svc in self.services:
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
        """Löscht oder bricht einen geplanten Timer ab."""
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

    def list_timers(self) -> list[dict[str, object]]:
        """Listet alle Timer sortiert nach Startzeit auf."""
        with self.timers_lock:
            res = [t.to_dict() for t in self.timers]
        res.sort(key=lambda x: x["start_time"])
        return res

    # -------------------------------------------------------------------------
    # Tuner / Transponder-Suchlauf
    # -------------------------------------------------------------------------
    def tune_transponder(
        self,
        freq_mhz: int,
        sr_ks: int = 22000,
        pol: str = "H",
        sat_lon: int = 192,
    ) -> tuple[bool, str]:
        if not self.tcp_sock:
            return False, "Nicht mit Dongle verbunden"

        freq_khz = freq_mhz * 1000 if freq_mhz < 100000 else freq_mhz
        with self.lock:
            try:
                # 1. Satellitenposition
                protocol.send_recv(
                    self.tcp_sock,
                    cmd_dvbs2_satellite_set(sat_lon, west=False, pol=pol),
                    2,
                    "0xF6/0x09 sat",
                )
                # 2. Tuner Transponder
                protocol.send_recv(
                    self.tcp_sock,
                    cmd_dvbs2_tuner_set(
                        freq_khz=freq_khz,
                        sr_khz=sr_ks,
                        pol=pol,
                        sat_lon_tenths=sat_lon,
                    ),
                    32,
                    "0xF6/0x01 tune",
                )
                # 3. Signal abfragen
                r = protocol.send_recv(self.tcp_sock, protocol.cmd_signal(), 17, "0x02 sig")
                status = parse_tuner_scan_status(r)
                return True, (
                    f"Transponder {freq_mhz} MHz {pol} {sr_ks} kS/s eingestellt. "
                    f"Lock={status.lock}, Signal={status.agc}%, Qualität={status.snr}%"
                )
            except Exception as e:
                return False, f"Fehler beim Einstellen: {e}"

    def start_scan(
        self,
        scan_type: int = SCAN_MANUAL,
        network_scan: bool = False,
        search_range: int = 0,
    ) -> tuple[bool, str]:
        if not self.tcp_sock:
            return False, "Nicht verbunden"
        if self.scan_in_progress:
            return False, "Suchlauf läuft bereits"

        self.scan_in_progress = True
        self._scan_stop.clear()
        self.scan_status = {
            "in_progress": True,
            "progress": 0,
            "lock": False,
            "agc": 0,
            "snr": 0,
            "freq": 0,
            "symbol_rate": 0,
            "tv_count": 0,
            "radio_count": 0,
        }

        try:
            with self.lock:
                protocol.send_recv(
                    self.tcp_sock,
                    cmd_scan_start_stop(
                        scan_type=scan_type,
                        network_scan=network_scan,
                        search_range=search_range,
                    ),
                    2,
                    "0xF6/0x10 start-scan",
                )
        except Exception as e:
            self.scan_in_progress = False
            return False, f"Konnte Suchlauf nicht starten: {e}"

        self._scan_thread = threading.Thread(target=self._scan_monitor_loop, daemon=True)
        self._scan_thread.start()
        return True, "Sendersuchlauf gestartet"

    def stop_scan(self) -> tuple[bool, str]:
        if not self.scan_in_progress:
            return False, "Kein Suchlauf aktiv"
        self._scan_stop.set()
        if self.tcp_sock:
            try:
                with self.lock:
                    protocol.send_recv(
                        self.tcp_sock,
                        cmd_scan_start_stop(scan_type=SCAN_STOP),
                        2,
                        "0xF6/0x10 stop-scan",
                    )
            except Exception:
                pass
        self.scan_in_progress = False
        self.scan_status["in_progress"] = False
        return True, "Suchlauf gestoppt"

    def _scan_monitor_loop(self) -> None:
        while not self._scan_stop.wait(0.5):
            if not self.tcp_sock:
                break
            try:
                with self.lock:
                    r = protocol.send_recv(self.tcp_sock, protocol.cmd_signal(), 17, "0x02 scan-poll")
                st = parse_tuner_scan_status(r)
                self.scan_status = {
                    "in_progress": st.scan_in_progress,
                    "progress": st.progress,
                    "lock": st.lock,
                    "agc": st.agc,
                    "snr": st.snr,
                    "freq": st.freq,
                    "symbol_rate": st.symbol_rate,
                    "tv_count": st.tv_count,
                    "radio_count": st.radio_count,
                }
                if not st.scan_in_progress:
                    log.info(
                        "Suchlauf abgeschlossen: %d TV, %d Radio gefunden.",
                        st.tv_count, st.radio_count,
                    )
                    self.scan_in_progress = False
                    # Kanalliste nach Suchlauf neu einlesen
                    self.refresh_channels()
                    break
            except Exception as e:
                log.debug("Scan-Poll Fehler: %s", e)
                break
        self.scan_in_progress = False
        self.scan_status["in_progress"] = False

    # -------------------------------------------------------------------------
    # M3U Playlist Generator
    # -------------------------------------------------------------------------
    def generate_m3u(self, base_url: str) -> str:
        lines = ["#EXTM3U"]
        channels_to_export = self.channels or [
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
            for s in self.services
        ]
        for ch in sorted(channels_to_export, key=lambda c: (c.lcn if c.lcn > 0 else 999999, c.name.lower())):
            tvg_id = f"wisi.{ch.service_id}"
            group = "Radio" if ch.is_radio else "Fernsehen"
            lines.append(
                f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="{ch.name}" '
                f'tvg-chno="{ch.lcn}" group-title="{group}",{ch.name}'
            )
            lines.append(f"{base_url.rstrip('/')}/api/stream/{ch.prog_idx}")
        return "\n".join(lines) + "\n"
