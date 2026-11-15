"""
decrypt.py – AES-128-ECB MPEG-TS-Link-Entschlüsselung für den WISI OR S2D Dongle
=================================================================================
DEFAULT_TS_KEY      – Statischer 16-Byte AES-Schlüssel aus dem APK
descramble_ts_block – Entschlüsselt einen Block von 188-Byte MPEG-TS-Paketen
decrypt_ts_file     – Entschlüsselt eine gespeicherte .ts-Datei (in-place oder in Zieldatei)
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import protocol

log = logging.getLogger("wisi.decrypt")

# Link-Verschlüsselungsschlüssel des Dongles laut APK
# (com.crenova.tv.dongle.dvb.sdk.ui.player.a.onDongleCommunicationStatusHelpText):
DEFAULT_TS_KEY: bytes = bytes.fromhex("1234567880ABCDEF1234567880ABCDEF")
_TS_CIPHER = Cipher(algorithms.AES(DEFAULT_TS_KEY), modes.ECB())


def descramble_ts_block(block: bytes, key: bytes | None = None) -> bytes:
    """
    Entschlüsselt die Link-Verschlüsselung der 188-Byte MPEG-TS-Pakete analog zum APK
    (onDongleCommunicationStatusHelpText.java, Zeilen 331–423):
      - Falls transport_scrambling_control == 2 ((pkt[3] >> 6) & 3 == 2) und Payload vorhanden:
        * Scrambling-Bit 7 in pkt[3] löschen (pkt[3] &= 0x7F)
        * Adaptation-Field (falls vorhanden, (pkt[3] & 0x30) == 0x30) unverändert überspringen
        * Payload-Vielfaches von 16 Bytes ((pay_len // 16) * 16) mit AES-128-ECB entschlüsseln
        * Restliche < 16 Bytes am Paketende unverändert belassen
      - Sonst: obere 2 Bits von pkt[3] löschen (pkt[3] &= 0x3F).
    """
    buf = bytearray(block)
    n_pkts = len(buf) // protocol.TS_PKT_SIZE
    cipher = _TS_CIPHER if key is None else Cipher(algorithms.AES(key), modes.ECB())
    decryptor = cipher.decryptor()
    for i in range(n_pkts):
        off = i * protocol.TS_PKT_SIZE
        if buf[off] != protocol.TS_SYNC:
            buf[off + 3] &= 0x3F
            continue
        b3 = buf[off + 3]
        scram = (b3 >> 6) & 3
        has_payload = ((b3 >> 4) & 1) == 1
        if scram == 2 and has_payload:
            buf[off + 3] = b3 & 0x7F
            has_adapt = (b3 & 0x30) == 0x30
            adapt_len = (buf[off + 4] + 1) if has_adapt else 0
            if 0 <= adapt_len < 184:
                pay_off = off + 4 + adapt_len
                pay_len = 184 - adapt_len
                enc_len = (pay_len // 16) * 16
                if enc_len > 0:
                    buf[pay_off : pay_off + enc_len] = decryptor.update(
                        bytes(buf[pay_off : pay_off + enc_len])
                    )
        else:
            buf[off + 3] = b3 & 0x3F
    return bytes(buf)


def decrypt_ts_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    """
    Entschlüsselt eine gespeicherte MPEG-TS-Datei blockweise.
    Wenn `output_path` None oder identisch mit `input_path` ist, wird die Datei
    über eine temporäre Datei sicher in-place überschrieben.
    """
    src = Path(input_path)
    if not src.is_file():
        raise FileNotFoundError(f"TS-Datei nicht gefunden: {src}")

    dst = Path(output_path) if output_path is not None else src
    in_place = dst.resolve() == src.resolve()
    tmp_dst = dst.with_suffix(dst.suffix + ".dec.tmp") if in_place else dst

    t0 = time.perf_counter()
    total_bytes = 0
    chunk_size = protocol.UDP_REQUEST_LEN  # 48128 Byte (256 * 188)

    log.info("Entschlüssele %s …", src)
    with src.open("rb") as fin, tmp_dst.open("wb") as fout:
        while chunk := fin.read(chunk_size):
            complete_len = len(chunk) - (len(chunk) % protocol.TS_PKT_SIZE)
            if complete_len > 0:
                fout.write(descramble_ts_block(chunk[:complete_len]))
            if len(chunk) > complete_len:
                fout.write(chunk[complete_len:])
            total_bytes += len(chunk)

    if in_place:
        tmp_dst.replace(dst)

    dt = time.perf_counter() - t0
    log.info(
        "Entschlüsselung abgeschlossen: %s (%.2f MiB, %d TS-Pakete in %.2f s)",
        dst,
        total_bytes / 1_048_576,
        total_bytes // protocol.TS_PKT_SIZE,
        dt,
    )
    return dst
