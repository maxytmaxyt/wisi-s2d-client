"""
sac.py – CI+ / SAC Handshake-Framing und Authentifizierung (0xFA/0x01..0x03)
===========================================================================
Extrahiert aus scan.py zur modularen Strukturierung unter 300 Zeilen.
"""
from __future__ import annotations

import struct

from ..protocol.connection import recv_exactly
from ..protocol import protocol

SAC_ROOT_SEED = b"LukeRanDolphCI+1"


def cmd_sac_poll_len() -> bytes:
    """0xFA/0x01 – SAC-Antwortlänge vom Dongle abfragen (6 Byte: fa 01 <sacFlag> 00 <len_BE>)."""
    return protocol.build_usbc(6, 0x80, 0xFA, 0x01)


def cmd_sac_read(length: int) -> bytes:
    """0xFA/0x02 – SAC-Antwortpaket (`length` Byte) vom Dongle lesen."""
    return protocol.build_usbc(length, 0x80, 0xFA, 0x02)


def cmd_sac_write(payload: bytes, sac_embedded: bool = False) -> bytes:
    """0xFA/0x03 – SAC-Anforderungspaket (`payload`) an den Dongle senden."""
    flag = b"\x01" if sac_embedded else b"\x00"
    return protocol.build_usbc(len(payload), 0x00, 0xFA, 0x03, flag) + payload


def sac_write_and_read_response(sock, lock, payload: bytes, sac_embedded: bool = False) -> tuple[int, bytes]:
    """Führt einen vollständigen 0xFA/0x03 → 0xFA/0x01 → 0xFA/0x02 Zyklus analog zu `C2002c.java` aus."""
    pkt = cmd_sac_write(payload, sac_embedded=sac_embedded)
    with lock:
        sock.sendall(pkt)
        usbs = recv_exactly(sock, protocol.USBS_LEN)
        if usbs[:4] != b"USBS":
            raise ValueError(f"0xFA/0x03: ungültiger USBS-Trailer ({usbs[:4]!r})")

        hdr = protocol.send_recv(sock, cmd_sac_poll_len(), 6, "0xFA/0x01 sac-len")
        if len(hdr) < 6 or hdr[0] != 0xFA or hdr[1] != 0x01:
            raise ValueError(f"0xFA/0x01: ungültiger Header ({hdr.hex()})")
        resp_len = struct.unpack(">H", hdr[4:6])[0]
        if resp_len < 4:
            raise ValueError(f"0xFA/0x01: Antwortlänge zu klein ({resp_len})")

        resp = protocol.send_recv(sock, cmd_sac_read(resp_len), resp_len, "0xFA/0x02 sac-read")
        if len(resp) < 4 or resp[0] != 0xFA or resp[1] != 0x02:
            raise ValueError(f"0xFA/0x02: ungültige Antwort ({resp[:4].hex()})")
        return resp[2], resp[4:]
