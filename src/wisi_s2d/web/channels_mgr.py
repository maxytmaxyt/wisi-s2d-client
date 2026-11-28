"""
channels_mgr.py – Senderlisten- und EPG-Verwaltung für den WISI Dongle
======================================================================
Lädt Kanallisten per TCP, führt EPG-XML-Abfragen durch und cacht die
Ergebnisse in epg.json für Offline-Betrieb.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import threading
from typing import TYPE_CHECKING

from ..cli import epg as epg_module
from ..core.channels import channels_to_services, fetch_channel_list
from ..core.models import FALLBACK_SERVICE, Channel, ServiceEntry

if TYPE_CHECKING:
    from .streamer import DongleManager

log = logging.getLogger("wisi.ui.channels")


class ChannelManager:
    """Verwaltet Kanäle, Dienste und EPG-Daten."""

    def __init__(self, manager: DongleManager) -> None:
        self.manager = manager
        self.channels: list[Channel] = []
        self.services: list[ServiceEntry] = []
        self.epg_data: dict[int, list[dict]] = {}
        self._load_cached_epg()

    def _load_cached_epg(self) -> None:
        epg_file = Path("epg.json")
        if not epg_file.is_file():
            return
        try:
            data = json.loads(epg_file.read_text(encoding="utf-8"))
            for ch in data.get("channels", []):
                sid = ch.get("service_id")
                events = ch.get("events", [])
                if sid is not None and events:
                    normalized_events = []
                    for ev in events:
                        ev_copy = dict(ev)
                        if "date" in ev_copy:
                            ev_copy["date"] = epg_module.normalize_epg_date(str(ev_copy["date"]))
                        normalized_events.append(ev_copy)
                    self.epg_data[sid] = normalized_events
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

    def refresh_channels(self) -> list[Channel]:
        if not self.manager.tcp_sock:
            if not self.services:
                self.services = [FALLBACK_SERVICE]
            return self.channels

        try:
            with self.manager.lock:
                channels = fetch_channel_list(self.manager.tcp_sock, self.manager.lock)
            if channels:
                self.channels = channels
                self.services = channels_to_services(channels)
                log.info("%d Kanäle geladen", len(channels))
        except Exception as e:
            log.warning("Fehler beim Laden der Kanalliste: %s", e)
        return self.channels

    def refresh_epg(self, limit: int | None = None) -> dict[int, list[dict]]:
        if not self.manager.tcp_sock or not self.services:
            return self.epg_data

        target_services = self.services[:limit] if limit else self.services
        stop_evt = threading.Event()
        try:
            epg_results = epg_module.enrich_with_epg(
                self.manager.tcp_sock, self.manager.lock, target_services, stop_evt
            )
            self.epg_data.update(epg_results)
            payload = {
                "device_ip": self.manager.ip,
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
