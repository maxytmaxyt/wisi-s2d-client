"""
dongle_info.py – 3-stufige Hardware-, System- und Versionsabfrage (0xFA/0x00, 0x07, 0x08)
========================================================================================
Extrahiert aus scan.py zur modularen Strukturierung unter 300 Zeilen.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import struct

from ..protocol import protocol

log = logging.getLogger("wisi.proto.info")


def cmd_dongle_info_phase1() -> bytes:
    """0xFA/0x00 – Hardware-/Session-Info Phase 1 (64 Byte, CMD_SECURE_CH_GET_DONGLE_INFO = 300)."""
    return protocol.build_usbc(64, 0x80, 0xFA, 0x00)


def cmd_dongle_info_phase2() -> bytes:
    """0xFA/0x07 – Hardware-/Session-Info Phase 2 (51 Byte, Modellname + SVN-Revision + VSC-ID)."""
    return protocol.build_usbc(51, 0x80, 0xFA, 0x07)


def cmd_dongle_info_phase3() -> bytes:
    """0xFA/0x08 – Hardware-/Session-Info Phase 3 (480 Byte, MAC/IP + Feature-Flags)."""
    return protocol.build_usbc(480, 0x80, 0xFA, 0x08)


@dataclass(frozen=True)
class DongleInfo:
    """Zusammengefasste Hardware- und Firmware-Informationen des Dongles."""
    tuner_type: int = 26
    tuner_name: str = "DVB-S2"
    customer_id: int = 0
    hw_version: int = 0
    sw_version: int = 0
    loader_version: int = 0
    cas_type: int = 0
    chip_id: str = ""
    serial_id: str = ""
    verify_code: str = ""
    usb_proto_ver: int = 2
    has_phase2: bool = False
    system_id: str = ""
    model_name: str = "WISI OR S2D"
    svn_revision: int = 0
    vsc_id: str = ""
    dongle_mac: str = ""
    dongle_ip: str = ""
    client_ip: str = ""
    new_way_cbw: int = 0
    clear_fta_stream: int = 0
    is_sat_setup_enabled: int = 0


def parse_dongle_info_phase1(data: bytes) -> dict[str, object]:
    """Parst die 64-Byte Phase-1-Antwort von 0xFA/0x00."""
    if len(data) < 32:
        return {}
    tuner_type = data[2]
    tuner_names = {26: "DVB-S2", 25: "DVB-S", 1: "DVB-T", 2: "DVB-C", 4: "ISDB-T"}
    hw_ver = struct.unpack_from(">H", data, 5)[0] if len(data) >= 7 else 0
    sw_ver = struct.unpack_from(">H", data, 7)[0] if len(data) >= 9 else 0
    loader_ver = data[9] if len(data) >= 10 else 0
    return {
        "tuner_type": tuner_type,
        "tuner_name": tuner_names.get(tuner_type, f"Unbekannt ({tuner_type})"),
        "customer_id": struct.unpack_from(">H", data, 3)[0] if len(data) >= 5 else 0,
        "hw_version": hw_ver,
        "hw_version_str": f"v{(hw_ver >> 8) & 0xFF}.{hw_ver & 0xFF} (0x{hw_ver:04X})" if hw_ver > 0 else "0",
        "sw_version": sw_ver,
        "sw_version_str": f"v{(sw_ver >> 8) & 0xFF}.{sw_ver & 0xFF} (0x{sw_ver:04X})" if sw_ver > 0 else "0",
        "loader_version": loader_ver,
        "loader_version_str": str(loader_ver),
        "cas_type": struct.unpack_from(">H", data, 10)[0] if len(data) >= 12 else 0,
        "chip_id": data[12:20].hex() if len(data) >= 20 else "",
        "serial_id": data[20:26].hex() if len(data) >= 26 else "",
        "verify_code": data[26:30].hex() if len(data) >= 30 else "",
        "usb_proto_ver": data[30] & 0x0F if len(data) >= 31 else 0,
        "has_phase2": bool(data[31]) if len(data) >= 32 else False,
        "system_id": data[32:48].hex() if len(data) >= 48 else "",
    }


def parse_dongle_info_phase2(data: bytes) -> dict[str, object]:
    """Parst die 51-Byte Phase-2-Antwort von 0xFA/0x07."""
    if len(data) < 35:
        return {}
    model_raw = data[3:35]
    model_name = model_raw.split(b"\x00")[0].decode("ascii", errors="replace").strip()
    svn_revision = struct.unpack_from(">I", data, 35)[0] if len(data) >= 39 else 0
    vsc_id = data[39:51].hex() if len(data) >= 51 else ""
    return {
        "model_name": model_name or "WISI OR S2D",
        "svn_revision": svn_revision,
        "vsc_id": vsc_id,
    }


def parse_dongle_info_phase3(data: bytes) -> dict[str, object]:
    """Parst die 480-Byte Phase-3-Antwort von 0xFA/0x08."""
    if len(data) < 25:
        return {}
    mac = ":".join(f"{b:02x}" for b in data[2:8]) if len(data) >= 8 else ""
    dongle_ip = ".".join(str(b) for b in data[8:12]) if len(data) >= 12 else ""
    client_ip = ".".join(str(b) for b in data[12:16]) if len(data) >= 16 else ""
    return {
        "dongle_mac": mac,
        "dongle_ip": dongle_ip,
        "client_ip": client_ip,
        "new_way_cbw": data[19] & 0x0F if len(data) > 19 else 0,
        "clear_fta_stream": data[21] & 0x0F if len(data) > 21 else 0,
        "is_sat_setup_enabled": data[24] & 0x0F if len(data) > 24 else 0,
    }


def fetch_dongle_info(sock, lock) -> dict[str, object]:
    """Holt Phase 1, Phase 2 und ggf. Phase 3 Dongle-Informationen über TCP 8802."""
    info: dict[str, object] = {
        "model_name": "WISI OR S2D",
        "tuner_type": 26,
        "tuner_name": "DVB-S2",
    }
    try:
        with lock:
            r1 = protocol.send_recv(sock, cmd_dongle_info_phase1(), 64, "0xFA/0x00 info1")
        if r1:
            info.update(parse_dongle_info_phase1(r1))
            log.info("Phase 1 Info: HW=%s SW=%s Chip=%s", info.get("hw_version"), info.get("sw_version"), info.get("chip_id"))
    except Exception as exc:
        log.warning("Phase 1 fehlgeschlagen: %s", exc)

    if info.get("has_phase2", True):
        try:
            with lock:
                r2 = protocol.send_recv(sock, cmd_dongle_info_phase2(), 51, "0xFA/0x07 info2")
            if r2:
                info.update(parse_dongle_info_phase2(r2))
                log.info("Phase 2 Info: Modell=%s SVN=%s", info.get("model_name"), info.get("svn_revision"))
        except Exception as exc:
            log.warning("Phase 2 fehlgeschlagen: %s", exc)

    try:
        with lock:
            r3 = protocol.send_recv(sock, cmd_dongle_info_phase3(), 480, "0xFA/0x08 info3")
        if r3:
            info.update(parse_dongle_info_phase3(r3))
            log.info("Phase 3 Info: MAC=%s IP=%s", info.get("dongle_mac"), info.get("dongle_ip"))
    except Exception as exc:
        log.debug("Phase 3 nicht verfügbar: %s", exc)

    return info
