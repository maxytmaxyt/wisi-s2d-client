"""
connection.py – TCP-Transporthelfer und APIX-Session-Aufbau (0xF6/0x16 + 0x17)
==============================================================================
recv_exactly – Liest exakt n Bytes vom TCP-Socket
send_recv    – Sendet USBC-Befehl und liest Nutzdaten + 13-Byte USBS-Trailer
connect      – Baut TCP-Verbindung auf und führt den APIX-Handshake aus
disconnect   – Schließt die TCP-Verbindung
"""
from __future__ import annotations

import logging
import socket
import time

log = logging.getLogger("wisi.proto")


def recv_exactly(
    sock: socket.socket,
    n: int,
    timeout: float = 4.0,
) -> bytes:
    """Liest exakt n Bytes mit Timeout. Gibt auch Teilergebnisse zurück."""
    sock.settimeout(timeout)
    buf = bytearray()
    try:
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                break
            buf.extend(chunk)
    except TimeoutError:
        pass
    finally:
        sock.settimeout(None)
    return bytes(buf)


def send_recv(
    sock: socket.socket,
    cmd: bytes,
    data_len: int,
    label: str = "",
    usbs_len: int = 13,
    recv_timeout: float = 4.0,
) -> bytes:
    """Sendet Befehl, liest Nutzdaten (data_len Byte) + USBS-Trailer."""
    sock.sendall(cmd)
    raw = recv_exactly(sock, data_len + usbs_len, timeout=recv_timeout)
    payload = raw[:data_len]
    if label:
        log.debug(
            "%-25s tx=%dB rx=%dB head=%s",
            label,
            len(cmd),
            len(raw),
            payload[: min(6, len(payload))].hex(),
        )
    return payload


def connect(
    ip: str,
    tcp_port: int = 8802,
    connect_timeout: float = 5.0,
) -> socket.socket | None:
    """
    Baut TCP-Verbindung auf und führt APIX-Init (0x16 + 0x17) durch.
    Gibt Socket zurück oder None bei Fehler.
    """
    from . import protocol

    log.info("Verbinde %s:%d …", ip, tcp_port)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(connect_timeout)
    try:
        sock.connect((ip, tcp_port))
    except (TimeoutError, OSError) as e:
        log.error("TCP fehlgeschlagen: %s", e)
        sock.close()
        return None
    sock.settimeout(None)

    r = protocol.send_recv(sock, protocol.cmd_16(), 12, "0x16 init")
    if len(r) < 3:
        log.error("0x16: keine Antwort")
        sock.close()
        return None
    status = r[2]
    log.info("0x16 status=0x%02X  gerät=%s", status, r[3:8].hex())

    r = protocol.send_recv(sock, protocol.cmd_17_init(), 4, "0x17 init")
    log.info("0x17 flag=0x%02X", r[2] if len(r) > 2 else 0xFF)

    if status != 0x01:
        log.info("Warte auf Bereitschaft …")
        for _ in range(10):
            time.sleep(0.2)
            r = protocol.send_recv(sock, protocol.cmd_16(), 12, "0x16 poll")
            if len(r) >= 3 and r[2] == 0x01:
                log.info("Dongle bereit.")
                break
        else:
            log.warning("Dongle meldet nicht 0x01 – weiter trotzdem.")
    return sock


def disconnect(sock: socket.socket) -> None:
    try:
        sock.close()
    except OSError:
        pass
    log.info("Verbindung getrennt.")
