"""
wisi_proto_legacy.py – Archivierte Protokoll-Definitionen für v1/v4 Reverse-Engineering
"""
import struct

DONGLE_IP = "192.168.178.32"
TCP_PORT = 8802
UDP_PORT = 8800

MAGIC_TAG = b"\xA0\xCB\x03\x37"
UDP_PAYLOAD = 256 * 188
TS_SYNC = 0x47

PRE_SECS = 5.0
STREAM_MS = 0.1
KA_SECS = 2.5


def usbc(data_len: int, flags: int, prefix: int, opcode: int, payload: bytes = b"") -> bytes:
    cdb = (bytes([prefix]) + b"APIX" + bytes([opcode]) + payload).ljust(16, b"\x00")
    return b"USBC" + MAGIC_TAG + struct.pack(">I", data_len) + bytes([flags, 0, 0x10]) + cdb


def tcp_16() -> bytes:
    return usbc(12, 0x80, 0xF6, 0x16)


def tcp_17() -> bytes:
    return usbc(4, 0x80, 0xF6, 0x17)


def tcp_epg_size(idx: int) -> bytes:
    return usbc(6, 0x80, 0xF6, 0x30, struct.pack(">I", idx))


def tcp_epg_data(idx: int, n: int) -> bytes:
    return usbc(n, 0x80, 0xF6, 0x31, struct.pack(">II", idx, n))


def tcp_evt_size(eid: int) -> bytes:
    return usbc(6, 0x80, 0xF6, 0x35, struct.pack(">I", eid))


def tcp_evt_data(eid: int, n: int) -> bytes:
    return usbc(n, 0x80, 0xF6, 0x36, struct.pack(">II", eid, n))


def udp_02() -> bytes:
    return usbc(0, 0x00, 0xF9, 0x02, b"\x01\x00")


def udp_0a() -> bytes:
    return usbc(UDP_PAYLOAD, 0x80, 0xF9, 0x0A)


def udp_01() -> bytes:
    return usbc(UDP_PAYLOAD, 0x80, 0xF9, 0x01)
