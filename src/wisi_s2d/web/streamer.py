"""
streamer.py – Hintergrund-Streaming-Engine und Gerätesteuerung für die WISI Web-UI
==================================================================================
DongleManager – Verwaltet TCP/UDP-Verbindungen, Senderliste, EPG, Tuner-Suchlauf,
                Live-Streaming über HTTP (für Browser-Player & VLC) und Aufnahmen.
"""
from __future__ import annotations

import logging
from pathlib import Path
import queue
import socket
import threading
from typing import Any

from ..protocol.keepalive import _keepalive_worker
from ..core.models import Channel, ServiceEntry
from ..protocol import protocol
from ..core.scan import fetch_dongle_info
from .channels_mgr import ChannelManager
from .playlist import generate_m3u_playlist
from .scanner import TunerScanner
from .scheduler import RECORDINGS_DIR, TIMERS_FILE, RecordingScheduler, TimerEntry
from .stream_engine import StreamEngine

log = logging.getLogger("wisi.ui.streamer")


class DongleManager:
    """Zentrale Steuerungs- und Streaming-Klasse für die Web-Oberfläche."""

    def __init__(self, default_ip: str = protocol.DEFAULT_IP):
        self.ip = default_ip
        self.tcp_sock: socket.socket | None = None
        self.lock = threading.RLock()
        self.keepalive_stop = threading.Event()
        self.keepalive_thread: threading.Thread | None = None

        self.dongle_info: dict[str, object] = {
            "model_name": "WISI OR S2D",
            "tuner_type": 26,
            "tuner_name": "DVB-S2",
        }

        # Signal-Monitoring
        self.signal_strength: int = 0
        self.signal_quality: int = 0
        self.signal_locked: bool = False
        self._signal_stop = threading.Event()
        self._signal_thread: threading.Thread | None = None

        # Subsysteme
        self.ch_mgr = ChannelManager(self)
        self.scheduler = RecordingScheduler(self)
        self.scanner = TunerScanner(self)
        self.engine = StreamEngine(self)

    # -------------------------------------------------------------------------
    # Delegierte Eigenschaften & Methoden (Kanäle & EPG)
    # -------------------------------------------------------------------------
    @property
    def channels(self) -> list[Channel]:
        return self.ch_mgr.channels

    @channels.setter
    def channels(self, val: list[Channel]) -> None:
        self.ch_mgr.channels = val

    @property
    def services(self) -> list[ServiceEntry]:
        return self.ch_mgr.services

    @services.setter
    def services(self, val: list[ServiceEntry]) -> None:
        self.ch_mgr.services = val

    @property
    def epg_data(self) -> dict[int, list[dict]]:
        return self.ch_mgr.epg_data

    def refresh_channels(self) -> list[Channel]:
        return self.ch_mgr.refresh_channels()

    def refresh_epg(self, limit: int | None = None) -> dict[int, list[dict]]:
        return self.ch_mgr.refresh_epg(limit)

    # -------------------------------------------------------------------------
    # Delegierte Eigenschaften & Methoden (Streaming Engine)
    # -------------------------------------------------------------------------
    @property
    def active_service(self) -> ServiceEntry | None:
        return self.engine.active_service

    @active_service.setter
    def active_service(self, val: ServiceEntry | None) -> None:
        self.engine.active_service = val

    @property
    def stream_stats(self) -> dict[str, Any]:
        return self.engine.stream_stats

    @property
    def stream_thread(self) -> threading.Thread | None:
        return self.engine.stream_thread

    def start_stream(self, prog_idx: int) -> bool:
        return self.engine.start_stream(prog_idx)

    def stop_stream(self) -> None:
        self.engine.stop_stream()

    def subscribe_client(self) -> queue.Queue[bytes]:
        return self.engine.subscribe_client()

    def unsubscribe_client(self, q: queue.Queue[bytes]) -> None:
        self.engine.unsubscribe_client(q)

    # -------------------------------------------------------------------------
    # Delegierte Eigenschaften & Methoden (Aufnahmen & Timer)
    # -------------------------------------------------------------------------
    @property
    def recording_active(self) -> bool:
        return self.scheduler.recording_active

    @property
    def recording_path(self) -> Path | None:
        return self.scheduler.recording_path

    @property
    def recording_start_time(self) -> float:
        return self.scheduler.recording_start_time

    @property
    def recording_bytes(self) -> int:
        return self.scheduler.recording_bytes

    @property
    def timers(self) -> list[TimerEntry]:
        return self.scheduler.timers

    @property
    def timers_lock(self) -> threading.RLock:
        return self.scheduler.timers_lock

    @property
    def active_timer_id(self) -> str | None:
        return self.scheduler.active_timer_id

    def start_recording(self, prog_idx: int | None = None, filename: str | None = None) -> tuple[bool, str]:
        return self.scheduler.start_recording(prog_idx, filename)

    def stop_recording(self) -> tuple[bool, str]:
        return self.scheduler.stop_recording()

    def list_recordings(self) -> list[dict[str, Any]]:
        return self.scheduler.list_recordings()

    def delete_recording(self, filename: str) -> tuple[bool, str]:
        return self.scheduler.delete_recording(filename)

    def add_timer(
        self, prog_idx: int, title: str = "", start_time: float = 0.0, duration_minutes: int = 60
    ) -> tuple[bool, str, TimerEntry | None]:
        return self.scheduler.add_timer(prog_idx, title, start_time, duration_minutes)

    def delete_timer(self, timer_id: str) -> tuple[bool, str]:
        return self.scheduler.delete_timer(timer_id)

    def list_timers(self) -> list[dict[str, Any]]:
        return self.scheduler.list_timers()

    # -------------------------------------------------------------------------
    # Delegierte Eigenschaften & Methoden (Tuner & Scan)
    # -------------------------------------------------------------------------
    @property
    def scan_in_progress(self) -> bool:
        return self.scanner.scan_in_progress

    @property
    def scan_status(self) -> dict[str, Any]:
        return self.scanner.scan_status

    def tune_transponder(
        self, freq_mhz: int, sr_ks: int = 22000, pol: str = "H", sat_lon: int = 192
    ) -> tuple[bool, str]:
        return self.scanner.tune_transponder(freq_mhz, sr_ks, pol, sat_lon)

    def start_scan(
        self, scan_type: int = 0, network_scan: bool = False, search_range: int = 0
    ) -> tuple[bool, str]:
        return self.scanner.start_scan(scan_type, network_scan, search_range)

    def stop_scan(self) -> tuple[bool, str]:
        return self.scanner.stop_scan()

    def generate_m3u(self, base_url: str) -> str:
        return generate_m3u_playlist(self.channels, self.services, base_url)

    # -------------------------------------------------------------------------
    # Verbindung
    # -------------------------------------------------------------------------
    def is_connected(self) -> bool:
        return self.tcp_sock is not None

    def get_dongle_info(self) -> dict[str, object]:
        """Liefert Dongle-Informationen und fragt sie bei Bedarf frisch ab."""
        if self.tcp_sock and not self.dongle_info.get("chip_id"):
            try:
                info = fetch_dongle_info(self.tcp_sock, self.lock)
                if info.get("chip_id") or info.get("sw_version"):
                    self.dongle_info = info
            except Exception as e:
                log.warning("Fehler beim Abruf der Dongle-Info: %s", e)
        return self.dongle_info

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

            try:
                self.dongle_info = fetch_dongle_info(self.tcp_sock, self.lock)
            except Exception as exc:
                log.warning("Hardware-Info Abruf fehlgeschlagen: %s", exc)

            self.keepalive_stop.clear()
            self.keepalive_thread = threading.Thread(
                target=_keepalive_worker,
                args=(self.tcp_sock, self.lock, self.keepalive_stop),
                daemon=True,
            )
            self.keepalive_thread.start()

        self.refresh_channels()

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
                    self.signal_strength = min(100, round(r[3] * 100 / 255))
                    self.signal_quality = min(100, round(r[4] * 100 / 255))
            except Exception:
                pass


__all__ = [
    "DongleManager",
    "RECORDINGS_DIR",
    "TIMERS_FILE",
    "TimerEntry",
]
