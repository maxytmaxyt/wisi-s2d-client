"""
scan.py – DVB-S2 Tuner/Suchlauf-Befehle (0xF6) & Dongle-Info/SAC-Framing (0xFA)
================================================================================
Verifiziert aus den dekompilierten SDK-Klassen der Original-App (TV2Smart / Crenova SDK):
  - com.crenova.tv.dongle.dvb.sdk.messages.onGetBouquetListXml (0xF6)
  - com.crenova.tv.dongle.dvb.sdk.messages.onDongleCommunicationStatus (0xFA)
  - com.crenova.tv.dongle.dvb.sdk.onDongleGetIntegerData (Zustandsmaschine)
  - com.crenova.tv.dongle.dvb.sdk.security.* (CI+ / SAC Handshake)
"""
from __future__ import annotations

from dataclasses import dataclass
import struct

from ..protocol import protocol

# ── Konstanten für DVB-S2 Polarisation & 22-kHz-Ton (Byte 21 / Byte 23) ─────
DVBS2_TUNER_TYPE = 0x04

POL_AUTO = 0x00  # Bits 4–5 = 00 (Auto / ON)
POL_H_18V = 0x10  # Bits 4–5 = 01 (Horizontal / 18 V)
POL_V_13V = 0x20  # Bits 4–5 = 10 (Vertikal / 13 V)
POL_OFF = 0x30    # Bits 4–5 = 11 (LNB-Spannung aus)

KHZ_AUTO = 0x00   # Bits 6–7 = 00 (22 kHz Auto)
KHZ_ON = 0x40     # Bits 6–7 = 01 (22 kHz Ein / High-Band)
KHZ_OFF = 0x80    # Bits 6–7 = 10 (22 kHz Aus / Low-Band)

# ── Suchlauf-Modi für 0xF6/0x10 (Byte 21) ────────────────────────────────────
SCAN_MANUAL = 0
SCAN_AUTO = 1
SCAN_NETWORK = 2
SCAN_STOP = 3


def _encode_dvbs2_mode_byte(pol: str = "AUTO", khz_22: str = "AUTO") -> int:
    pol_norm = pol.strip().upper()
    if pol_norm in ("H", "18V", "HORIZONTAL"):
        pol_bits = POL_H_18V
    elif pol_norm in ("V", "13V", "VERTICAL"):
        pol_bits = POL_V_13V
    elif pol_norm == "OFF":
        pol_bits = POL_OFF
    else:
        pol_bits = POL_AUTO

    khz_norm = khz_22.strip().upper()
    if khz_norm == "ON":
        khz_bits = KHZ_ON
    elif khz_norm == "OFF":
        khz_bits = KHZ_OFF
    else:
        khz_bits = KHZ_AUTO

    return DVBS2_TUNER_TYPE | pol_bits | khz_bits


# ─────────────────────────────────────────────────────────────────────────────
# DVB-S2 LNB / DiSEqC / Satellit / Transponder / Suchlauf (0xF6)
# ─────────────────────────────────────────────────────────────────────────────

def cmd_dvbs2_lnb_set(
    lnb1_mhz: int = 9750,
    lnb2_mhz: int = 10600,
    center_freq_mhz: int = 11700,
    unicable_sat: int = 0,
    band_freq_mhz: int = 0,
) -> bytes:
    """0xF6/0x07 – DVB-S2 LNB-Konfiguration (CMD_TUNER_DVBS2_SET_LNB = 126).

    Standardwerte entsprechen einem Universal-Ku-Band-LNB (9750/10600/11700 MHz).
    CDB-Payload (Bytes 21–30):
      [lnb1_hi, lnb1_lo, lnb2_hi, lnb2_lo, center_hi, center_lo,
       unicable_sat, band_hi, band_lo, 0x00]
    Antwort: 2 Byte.
    """
    payload = struct.pack(
        ">HHHBHB",
        lnb1_mhz & 0xFFFF,
        lnb2_mhz & 0xFFFF,
        center_freq_mhz & 0xFFFF,
        unicable_sat & 0xFF,
        band_freq_mhz & 0xFFFF,
        0,
    )
    return protocol.build_usbc(2, 0x80, 0xF6, 0x07, payload)


def cmd_dvbs2_diseqc_set(
    diseqc11: int = 0,
    diseqc12: int = 0,
    usals1: int = 0,
    usals2: int = 0,
    usals3: int = 0,
    usals4: int = 0,
) -> bytes:
    """0xF6/0x08 – DVB-S2 DiSEqC 1.0/1.1/1.2 & USALS-Konfiguration (CMD = 127).

    CDB-Payload (Bytes 21–30):
      [diseqc11, diseqc12, usals1_hi, usals1_lo, usals2_hi, usals2_lo,
       usals3_hi, usals3_lo, usals4_hi, usals4_lo]
    Antwort: 2 Byte.
    """
    payload = struct.pack(
        ">BBHHHH",
        diseqc11 & 0xFF,
        diseqc12 & 0xFF,
        usals1 & 0xFFFF,
        usals2 & 0xFFFF,
        usals3 & 0xFFFF,
        usals4 & 0xFFFF,
    )
    return protocol.build_usbc(2, 0x80, 0xF6, 0x08, payload)


def cmd_dvbs2_satellite_set(
    sat_lon_tenths: int = 192,
    west: bool = False,
    pol: str = "AUTO",
    khz_22: str = "AUTO",
) -> bytes:
    """0xF6/0x09 – DVB-S2 Satellitenposition setzen (CMD_TUNER_DVBS2_SET_SATELLITE = 132).

    sat_lon_tenths: Orbitposition in 0,1° (z. B. 192 für Astra 19,2° Ost).
    west: False = Ost (Bit 7 in Byte 21 = 0), True = West (Bit 7 in Byte 21 = 1).
    CDB-Payload (Bytes 21–23): [lon_hi | west_bit, lon_lo, mode_byte].
    Antwort: 2 Byte.
    """
    lon_hi = ((sat_lon_tenths >> 8) & 0x7F) | (0x80 if west else 0x00)
    lon_lo = sat_lon_tenths & 0xFF
    mode_byte = _encode_dvbs2_mode_byte(pol, khz_22)
    return protocol.build_usbc(2, 0x80, 0xF6, 0x09, bytes([lon_hi, lon_lo, mode_byte]))


def cmd_dvbs2_tuner_set(
    freq_khz: int,
    sr_khz: int = 22000,
    pol: str = "H",
    sat_lon_tenths: int = 192,
    west: bool = False,
    khz_22: str = "AUTO",
) -> bytes:
    """0xF6/0x01 – DVB-S2 Transponder-Tune (CMD_TUNER_DVBS2_SET = 125).

    CDB-Payload (Bytes 21–30):
      Byte 21:     0x04 | pol_bits | khz_bits
      Byte 22–23:  satLongitude (uint16 BE, Bit 7 von Byte 22 = West)
      Byte 24–25:  Symbolrate in kS/s (uint16 BE, z. B. 22000)
      Byte 26–28:  Frequenz in kHz (uint24 BE)
      Byte 29–30:  0x00 0x00
    Antwort: 32 Byte.
    """
    mode_byte = _encode_dvbs2_mode_byte(pol, khz_22)
    lon_hi = ((sat_lon_tenths >> 8) & 0x7F) | (0x80 if west else 0x00)
    lon_lo = sat_lon_tenths & 0xFF
    sr_bytes = struct.pack(">H", sr_khz & 0xFFFF)
    freq_bytes = struct.pack(">I", freq_khz & 0xFFFFFF)[1:]
    payload = bytes([mode_byte, lon_hi, lon_lo]) + sr_bytes + freq_bytes + b"\x00\x00"
    return protocol.build_usbc(32, 0x80, 0xF6, 0x01, payload)


def cmd_scan_start_stop(
    scan_type: int = SCAN_MANUAL,
    network_scan: bool = False,
    order_by: int = 0,
    search_range: int = 0,
    sort_mode: int = 0,
) -> bytes:
    """0xF6/0x10 – Sendersuchlauf starten oder stoppen (CMD_TUNER_SCAN = 111 / 704).

    scan_type (Byte 21):
      0 = SCAN_MANUAL, 1 = SCAN_AUTO, 2 = SCAN_NETWORK, 3 = SCAN_STOP
    flags (Byte 22):
      Bit 0:   network_scan (0 = Nein, 1 = NIT-Netzwerksuche)
      Bit 1–2: order_by (0 = Default, 1 = SID, 2 = Name)
      Bit 3–5: search_range (0 = Alle, 1 = FTA, 2 = TV, 3 = Radio, 4 = FTA+TV, 5 = FTA+Radio)
      Bit 6–7: sort_mode
    Antwort: 2 Byte (f6 10).
    """
    flags_byte = (
        (1 if network_scan else 0)
        | ((order_by & 0x03) << 1)
        | ((search_range & 0x07) << 3)
        | ((sort_mode & 0x03) << 6)
    )
    return protocol.build_usbc(2, 0x80, 0xF6, 0x10, bytes([scan_type & 0xFF, flags_byte]))


@dataclass(frozen=True)
class TunerScanStatus:
    """Geparste 17-Byte-Antwort von 0xF6/0x02 (CMD_TUNER_STATUS = 112)."""
    lock: bool
    tune_fail: bool
    agc: int
    snr: int
    scan_in_progress: bool
    progress: int
    freq: int
    symbol_rate: int
    mode: int
    tv_count: int
    radio_count: int


def parse_tuner_scan_status(data: bytes) -> TunerScanStatus:
    """Parst die 17-Byte-Antwort von 0xF6/0x02 analog zu SDK `onDongleGetIntegerData.java`."""
    if len(data) < 17:
        raise ValueError(f"0xF6/0x02 Antwort zu kurz ({len(data)} Byte, erwartet 17)")
    return TunerScanStatus(
        lock=bool(data[2] & 0x01),
        tune_fail=bool(data[2] & 0x80),
        agc=data[3],
        snr=data[4],
        scan_in_progress=(data[5] == 1),
        progress=data[6],
        freq=(data[7] << 16) | (data[8] << 8) | data[9],
        symbol_rate=(data[10] << 8) | data[11],
        mode=data[12],
        tv_count=(data[13] << 8) | data[14],
        radio_count=(data[15] << 8) | data[16],
    )


def cmd_scan_result_size(dvbs2: bool = True) -> bytes:
    """0xF6/0x11 – Größe der gefundenen Kanalliste nach Suchlauf abfragen (CMD = 113)."""
    return protocol.build_usbc(4 if dvbs2 else 6, 0x80, 0xF6, 0x11)


def cmd_scan_result_data(length: int) -> bytes:
    """0xF6/0x12 – Gefundene Kanalliste (XML) nach Suchlauf abrufen (CMD = 114)."""
    return protocol.build_usbc(length, 0x80, 0xF6, 0x12)


# ─────────────────────────────────────────────────────────────────────────────
# Re-Exports aus dongle_info und sac
# ─────────────────────────────────────────────────────────────────────────────
from .dongle_info import (
    DongleInfo,
    cmd_dongle_info_phase1,
    cmd_dongle_info_phase2,
    cmd_dongle_info_phase3,
    fetch_dongle_info,
    parse_dongle_info_phase1,
    parse_dongle_info_phase2,
    parse_dongle_info_phase3,
)
from .sac import (
    SAC_ROOT_SEED,
    cmd_sac_poll_len,
    cmd_sac_read,
    cmd_sac_write,
    sac_write_and_read_response,
)


__all__ = [
    "DVBS2_TUNER_TYPE",
    "DongleInfo",
    "KHZ_AUTO",
    "KHZ_OFF",
    "KHZ_ON",
    "POL_AUTO",
    "POL_H_18V",
    "POL_OFF",
    "POL_V_13V",
    "SAC_ROOT_SEED",
    "SCAN_AUTO",
    "SCAN_MANUAL",
    "SCAN_NETWORK",
    "SCAN_STOP",
    "TunerScanStatus",
    "cmd_dongle_info_phase1",
    "cmd_dongle_info_phase2",
    "cmd_dongle_info_phase3",
    "cmd_dvbs2_diseqc_set",
    "cmd_dvbs2_lnb_set",
    "cmd_dvbs2_satellite_set",
    "cmd_dvbs2_tuner_set",
    "cmd_sac_poll_len",
    "cmd_sac_read",
    "cmd_sac_write",
    "cmd_scan_result_data",
    "cmd_scan_result_size",
    "cmd_scan_start_stop",
    "fetch_dongle_info",
    "parse_dongle_info_phase1",
    "parse_dongle_info_phase2",
    "parse_dongle_info_phase3",
    "parse_tuner_scan_status",
    "sac_write_and_read_response",
]
