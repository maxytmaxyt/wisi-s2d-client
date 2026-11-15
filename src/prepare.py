"""
prepare.py – Kanalwechsel (0xF6/0x03), Kanal-Info (0x32/0x33) und Signalprüfung (0x02)
======================================================================================
prepare_channel          – Tunet auf den Dienst und prüft die Signalstärke
get_last_prepared_prog_idx – Gibt den zuletzt vorbereiteten prog_idx zurück
reset_prepared_prog_idx  – Setzt den gespeicherten prog_idx zurück
"""
from __future__ import annotations

import logging
import socket
import struct
import threading
import time

import protocol
from models import ServiceEntry

log = logging.getLogger("wisi.stream")

_last_prepared_prog_idx: int | None = None


def get_last_prepared_prog_idx() -> int | None:
    return _last_prepared_prog_idx


def reset_prepared_prog_idx() -> None:
    global _last_prepared_prog_idx
    _last_prepared_prog_idx = None


def prepare_channel(
    sock: socket.socket,
    lock: threading.Lock,
    svc: ServiceEntry,
) -> None:
    """0xF6/0x03 Kanalwechsel (mit Lock-Retry) → 0x32/0x33 ch_Info → 0x02 Signal-Poll."""
    global _last_prepared_prog_idx
    with lock:
        r = protocol.send_recv(sock, protocol.cmd_prepare(svc.prog_idx), 4, "0x03 prepare")

    # Laut APK (onDongleGetIntegerData.onDongleCommunicationStatus, Zeilen 1293–1322):
    # Antwort ist f6 03 <signalLock> <isFta>. Bei signalLock == 0 bis zu 3x nach 250 ms wiederholen.
    retry = 0
    while len(r) >= 3 and r[2] == 0 and retry < 3:
        retry += 1
        time.sleep(0.25)
        with lock:
            r = protocol.send_recv(
                sock,
                protocol.cmd_prepare(svc.prog_idx),
                4,
                f"0x03 retry [{retry}/3]",
            )

    signal_lock = r[2] if len(r) >= 3 else 0
    is_fta = r[3] if len(r) >= 4 else 0
    log.info(
        "Tune 0xF6/0x03: idx=%d  sid=%d  prog_idx=0x%08X  lock=%d  fta=%d  (%s)",
        svc.pat_index, svc.service_id, svc.prog_idx, signal_lock, is_fta, svc.name,
    )
    _last_prepared_prog_idx = svc.prog_idx

    with lock:
        r = protocol.send_recv(sock, protocol.cmd_chinfo_size(svc.prog_idx), 6, "0x32 chinfo-size")
    if len(r) >= 6:
        ci_size = struct.unpack(">I", r[2:6])[0]
        if ci_size > 0:
            with lock:
                r2 = protocol.send_recv(
                    sock, protocol.cmd_chinfo_data(svc.prog_idx, ci_size),
                    ci_size, "0x33 chinfo",
                )
            xml_start = r2.find(b"<")
            chinfo_text = (
                r2[xml_start:ci_size].decode("utf-8", "replace").strip()
                if xml_start >= 0
                else r2[:min(80, ci_size)].decode("utf-8", "replace")
            )
            log.debug("ch_Info: %s", chinfo_text)

    for attempt in range(3):
        with lock:
            r = protocol.send_recv(
                sock, protocol.cmd_signal(), 17,
                f"0x02 signal [{attempt + 1}/3]",
            )
        if len(r) >= 5:
            log.info("Signal: Stärke=%d%%  Qualität=%d%%", r[3], r[4])
            if r[3] >= 50:
                return
        if attempt < 2:
            time.sleep(0.5)
    log.warning("Signal schwach – weiter trotzdem.")
