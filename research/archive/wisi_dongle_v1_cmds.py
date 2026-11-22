"""
wisi_dongle_v1_cmds.py – Befehlsdefinitionen für wisi_dongle_v1.py
"""
import socket
import struct

MAGIC_TAG = b"\xA0\xCB\x03\x37"
TS_PACKETS_PER_BLOCK = 256
TS_PACKET_SIZE = 188
UDP_PAYLOAD_EXPECTED = TS_PACKETS_PER_BLOCK * TS_PACKET_SIZE
TS_SYNC_BYTE = 0x47


def make_usbc(data_length: int, flags: int, apix_cmd: bytes) -> bytes:
    if len(apix_cmd) != 16:
        raise ValueError(f"APIX-Befehl muss 16 Byte lang sein, hat {len(apix_cmd)}")
    cbw = (
        b"USBC"
        + MAGIC_TAG
        + struct.pack(">I", data_length)
        + bytes([flags, 0x00, 0x10])
        + apix_cmd
    )
    assert len(cbw) == 31
    return cbw


def apix(opcode: int, payload: bytes = b"") -> bytes:
    raw = bytes([0xF6, opcode]) + payload
    if len(raw) > 16:
        raise ValueError("APIX-Payload zu lang")
    return raw.ljust(16, b"\x00")


def cmd_init_16() -> bytes:
    return make_usbc(12, 0x80, apix(0x16))


def cmd_init_17() -> bytes:
    return make_usbc(4, 0x80, apix(0x17))


def cmd_pre_stream_02() -> bytes:
    return make_usbc(0, 0x80, apix(0x02))


def cmd_pre_stream_0a() -> bytes:
    return make_usbc(UDP_PAYLOAD_EXPECTED, 0x80, apix(0x0A))


def cmd_stream_01() -> bytes:
    return make_usbc(UDP_PAYLOAD_EXPECTED, 0x80, apix(0x01, b"APIX"))


def cmd_epg_size(prog_idx: int) -> bytes:
    return make_usbc(6, 0x80, apix(0x30, struct.pack(">I", prog_idx)))


def cmd_epg_data(prog_idx: int, length: int) -> bytes:
    return make_usbc(length, 0x80, apix(0x31, struct.pack(">I", prog_idx) + struct.pack(">I", length)))


def cmd_event_size(evt_id: int) -> bytes:
    return make_usbc(6, 0x80, apix(0x35, struct.pack(">I", evt_id)))


def cmd_event_data(evt_id: int, length: int) -> bytes:
    return make_usbc(length, 0x80, apix(0x36, struct.pack(">I", evt_id) + struct.pack(">I", length)))


def recv_exact(sock: socket.socket, n: int, timeout: float = 5.0) -> bytes:
    sock.settimeout(timeout)
    buf = bytearray()
    try:
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise OSError("Verbindung unerwartet geschlossen")
            buf.extend(chunk)
    finally:
        sock.settimeout(None)
    return bytes(buf)


def drain(sock: socket.socket, expected_data_bytes: int = 0, drain_timeout: float = 1.5) -> bytes:
    total = expected_data_bytes + 13
    sock.settimeout(drain_timeout)
    buf = bytearray()
    try:
        while len(buf) < total:
            chunk = sock.recv(min(4096, total - len(buf)))
            if not chunk:
                break
            buf.extend(chunk)
            if len(buf) >= total:
                break
    except socket.timeout:
        pass
    finally:
        sock.settimeout(None)
    return bytes(buf)


def send_cmd(sock: socket.socket, cmd: bytes, expected_data: int = 0) -> bytes:
    sock.sendall(cmd)
    return drain(sock, expected_data)
