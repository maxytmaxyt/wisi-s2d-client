"""
scanner.py – Transponder-Tuning und Sendersuchlauf für den WISI Dongle
=====================================================================
Steuert DVB-S2-Tuning-Parameter, DiSEqC, Satellitenposition und den
automatischen/manuellen Sendersuchlauf über das WISI TCP-Protokoll.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

from ..protocol import protocol
from ..core.scan import (
    SCAN_MANUAL,
    SCAN_STOP,
    cmd_dvbs2_satellite_set,
    cmd_dvbs2_tuner_set,
    cmd_scan_start_stop,
    parse_tuner_scan_status,
)

if TYPE_CHECKING:
    from ui.streamer import DongleManager

log = logging.getLogger("wisi.ui.scanner")


class TunerScanner:
    """Verwaltet Transponder-Tuning und Kanalsuchlauf."""

    def __init__(self, manager: DongleManager) -> None:
        self.manager = manager
        self.scan_in_progress: bool = False
        self.scan_status: dict[str, Any] = {
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

    def tune_transponder(
        self,
        freq_mhz: int,
        sr_ks: int = 22000,
        pol: str = "H",
        sat_lon: int = 192,
    ) -> tuple[bool, str]:
        if not self.manager.tcp_sock:
            return False, "Nicht mit Dongle verbunden"

        freq_khz = freq_mhz * 1000 if freq_mhz < 100000 else freq_mhz
        with self.manager.lock:
            try:
                protocol.send_recv(
                    self.manager.tcp_sock,
                    cmd_dvbs2_satellite_set(sat_lon, west=False, pol=pol),
                    2,
                    "0xF6/0x09 sat",
                )
                protocol.send_recv(
                    self.manager.tcp_sock,
                    cmd_dvbs2_tuner_set(
                        freq_khz=freq_khz,
                        sr_khz=sr_ks,
                        pol=pol,
                        sat_lon_tenths=sat_lon,
                    ),
                    32,
                    "0xF6/0x01 tune",
                )
                r = protocol.send_recv(self.manager.tcp_sock, protocol.cmd_signal(), 17, "0x02 sig")
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
        if not self.manager.tcp_sock:
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
            with self.manager.lock:
                protocol.send_recv(
                    self.manager.tcp_sock,
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
        if self.manager.tcp_sock:
            try:
                with self.manager.lock:
                    protocol.send_recv(
                        self.manager.tcp_sock,
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
            if not self.manager.tcp_sock:
                break
            try:
                with self.manager.lock:
                    r = protocol.send_recv(self.manager.tcp_sock, protocol.cmd_signal(), 17, "0x02 scan-poll")
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
                    self.manager.refresh_channels()
                    break
            except Exception as e:
                log.debug("Scan-Poll Fehler: %s", e)
                break
        self.scan_in_progress = False
        self.scan_status["in_progress"] = False
