"""
protocol.py – WISI OR S2D / TiViCon APIX-Protokoll: Shared Layer
Alle USBC-Builder und Konstanten (TCP-Transporthelfer sind in connection.py).
Kein eigener Einstiegspunkt – wird von allen anderen Modulen importiert.
"""
from __future__ import annotations

import logging
import struct

from connection import connect, disconnect, recv_exactly, send_recv

log = logging.getLogger("wisi.proto")

# ── Netzwerk ─────────────────────────────────────────────────────────────────
DEFAULT_IP   = "192.168.178.32"
TCP_PORT     = 8802
UDP_PORT     = 8800
MAGIC_TAG    = b"\xA0\xCB\x03\x37"

# ── Timing ───────────────────────────────────────────────────────────────────
CONNECT_TIMEOUT  = 5.0
RECV_TIMEOUT     = 4.0
KEEPALIVE_INTVL  = 2.0
SIGNAL_INTVL     = 3.0

# ── UDP / TS ─────────────────────────────────────────────────────────────────
UDP_REQUEST_LEN   = 0xBC00       # 48 128 Byte – data_len-Feld im F9/01 und F9/0A CBW
UDP_RESPONSE_SIZE = 48_205       # 0xBC00 + 64 SDK-Header + 13 USBS-Trailer
TS_PKT_SIZE       = 188
TS_SYNC           = 0x47
USBS_LEN          = 13           # USBS-Status-Trailer Länge


# ─────────────────────────────────────────────────────────────────────────────
# USBC-Builder
# ─────────────────────────────────────────────────────────────────────────────

def build_usbc(data_len: int, flags: int,
               prefix: int, opcode: int,
               payload: bytes = b"") -> bytes:
    """
    31-Byte USBC Command Block (USB Bulk-Only Transport CBW).
    data_len wird im APIX-Protokoll als Big-Endian kodiert.

    Flags: 0x80 = Lesen (Host ← Gerät), 0x00 = Schreiben (Host → Gerät)
    """
    cdb = (bytes([prefix]) + b"APIX" + bytes([opcode]) + payload).ljust(16, b"\x00")
    assert len(cdb) == 16, f"CDB muss 16 Byte sein, hat {len(cdb)}"
    return (b"USBC" + MAGIC_TAG
            + struct.pack(">I", data_len)
            + bytes([flags, 0x00, 0x10])
            + cdb)


# ── TCP-Befehle (prefix = 0xF6 / 0xF8) ──────────────────────────────────────

def cmd_16()         -> bytes: return build_usbc(12, 0x80, 0xF6, 0x16)
def cmd_17_init()    -> bytes: return build_usbc(4,  0x80, 0xF6, 0x17)
def cmd_17_confirm() -> bytes: return build_usbc(4,  0x80, 0xF6, 0x17, b"\x01\x00\x00\x00")
def cmd_signal()     -> bytes: return build_usbc(17, 0x80, 0xF6, 0x02)


def cmd_stream_release() -> bytes:
    """0xF8/0x07 – Stream/Aufnahme stoppen (31B USBC + 4B Host-to-Device Payload)."""
    return build_usbc(4, 0x00, 0xF8, 0x07) + b"\x01\x00\x00\x00"


def cmd_epg_size(prog_idx: int) -> bytes:
    return build_usbc(6, 0x80, 0xF6, 0x30, b"\x00\x00\x00\x00" + struct.pack(">I", prog_idx))


def cmd_epg_data(prog_idx: int, offset: int, length: int) -> bytes:
    return build_usbc(
        length, 0x80, 0xF6, 0x31,
        b"\x00\x00\x00\x00" + struct.pack(">I", prog_idx) + struct.pack(">H", offset),
    )


def cmd_evtdesc_size(prog_idx: int, event_id: int = 0) -> bytes:
    return build_usbc(
        6, 0x80, 0xF6, 0x35,
        b"\x00\x00" + struct.pack(">HI", event_id & 0xFFFF, prog_idx),
    )


def cmd_evtdesc_data(prog_idx: int, length: int, event_id: int = 0) -> bytes:
    return build_usbc(
        length, 0x80, 0xF6, 0x36,
        b"\x00\x00" + struct.pack(">HI", event_id & 0xFFFF, prog_idx),
    )


def cmd_prepare(prog_idx: int) -> bytes:
    """0xF6/0x03 – Kanalwechsel per prog_idx (ACTION_CHANGE_CHANNEL_BY_PROGIDX).

    Payload (Bytes 21–28): Modus 0x00000002 + 32-Bit prog_idx des Senders (Big-Endian).
    Antwort (4 Byte): f6 03 <signalLock> <isFta>.
    """
    return build_usbc(
        4, 0x80, 0xF6, 0x03,
        b"\x00\x00\x00\x02" + struct.pack(">I", prog_idx),
    )


def cmd_chinfo_size(prog_idx: int) -> bytes:
    return build_usbc(6, 0x80, 0xF6, 0x32, b"\x00\x00\x00\x00" + struct.pack(">I", prog_idx))


def cmd_chinfo_data(prog_idx: int, length: int) -> bytes:
    return build_usbc(length, 0x80, 0xF6, 0x33, b"\x00\x00\x00\x00" + struct.pack(">I", prog_idx))


def cmd_tune(channel_index: int) -> bytes:
    """0xF6/0x01 – Legacy-Tune-Befehl."""
    return build_usbc(2, 0x80, 0xF6, 0x01, struct.pack(">H", channel_index & 0xFFFF))


def cmd_probe(opcode: int) -> bytes:
    """Sendet einen unbekannten Opcode (0xF6) mit minimalen Daten – für Opcode-Scan."""
    return build_usbc(4, 0x80, 0xF6, opcode)


# ── UDP-Befehle (prefix = 0xF9) ─────────────────────────────────────────────

def cmd_udp_init() -> bytes:
    """0xF9/0x02 – einmalige Stream-Initialisierung."""
    return build_usbc(0, 0x00, 0xF9, 0x02, b"\x01")


def cmd_udp_service_db() -> bytes:
    """Legacy-Builder: Die analysierte APK verwendet F9/0A für einen Speedtest."""
    return build_usbc(UDP_REQUEST_LEN, 0x80, 0xF9, 0x0A)


def cmd_udp_ts_block(first: bool = False) -> bytes:
    """0xF9/0x01 – MPEG-TS-Block anfordern (Pull-Mechanismus).

    first=True  → byte21=0x00 (erster Block / nach erfolgreichem Block)
    first=False → byte21=0x01 (Wiederholung nach Timeout/Fehler)
    """
    byte21 = b"\x00" if first else b"\x01"
    return build_usbc(UDP_REQUEST_LEN, 0x80, 0xF9, 0x01, byte21)


__all__ = [
    "CONNECT_TIMEOUT",
    "DEFAULT_IP",
    "KEEPALIVE_INTVL",
    "MAGIC_TAG",
    "RECV_TIMEOUT",
    "SIGNAL_INTVL",
    "TCP_PORT",
    "TS_PKT_SIZE",
    "TS_SYNC",
    "UDP_PORT",
    "UDP_REQUEST_LEN",
    "UDP_RESPONSE_SIZE",
    "USBS_LEN",
    "build_usbc",
    "cmd_16",
    "cmd_17_confirm",
    "cmd_17_init",
    "cmd_chinfo_data",
    "cmd_chinfo_size",
    "cmd_epg_data",
    "cmd_epg_size",
    "cmd_evtdesc_data",
    "cmd_evtdesc_size",
    "cmd_prepare",
    "cmd_probe",
    "cmd_signal",
    "cmd_stream_release",
    "cmd_tune",
    "cmd_udp_init",
    "cmd_udp_service_db",
    "cmd_udp_ts_block",
    "connect",
    "disconnect",
    "recv_exactly",
    "send_recv",
]
