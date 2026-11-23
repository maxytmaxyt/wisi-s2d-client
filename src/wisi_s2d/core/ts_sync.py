"""
ts_sync.py – Hilfsfunktionen zur Synchronisation und Validierung von MPEG-TS-Paketen
===================================================================================
Überprüft Sequenznummern von UDP-Datagrammen und sucht 0x47-Sync-Bytes
für exakte 188-Byte-Paketausrichtung.
"""
from __future__ import annotations

from ..protocol import protocol


def align_ts_packets(
    data: bytes,
    last_seq: int,
) -> tuple[bytes, int, bool]:
    """
    Extrahiert aus einem empfangenen UDP-Block ausgerichtete TS-Pakete.

    Rückgabe:
        (ts_chunk, new_last_seq, retry_needed)
        - ts_chunk: Extrahierte Roh-TS-Pakete (Vielfaches von 188 Bytes)
        - new_last_seq: Aktualisierte Sequenznummer
        - retry_needed: True wenn Paket verworfen werden muss und Retry nötig ist
    """
    if len(data) < protocol.TS_PKT_SIZE * 4:
        return b"", last_seq, True

    if len(data) >= protocol.UDP_REQUEST_LEN + 64:
        seq = data[protocol.UDP_REQUEST_LEN + 12]
        if last_seq < seq:
            last_seq = seq
        elif seq == 0 and last_seq == 255:
            # Normaler Wraparound 255 → 0: Sequenz zurücksetzen
            last_seq = -1
        elif last_seq == 255 and seq != 0:
            # Wraparound übersprungen (255 → >0): akzeptieren und weiter
            last_seq = seq
        elif seq == 0 and last_seq != 255:
            # Wraparound ohne vorherigen 255er: akzeptieren
            last_seq = -1
        else:
            # Duplikat oder Rücksprung: Block verwerfen
            return b"", last_seq, True
        payload = data[:protocol.UDP_REQUEST_LEN]
    elif len(data) > protocol.UDP_REQUEST_LEN:
        payload = data[:protocol.UDP_REQUEST_LEN]
    else:
        payload = data

    sync_offset = payload.find(bytes([protocol.TS_SYNC]))
    while sync_offset >= 0:
        if (
            sync_offset + 3 * protocol.TS_PKT_SIZE < len(payload)
            and all(
                payload[sync_offset + i * protocol.TS_PKT_SIZE] == protocol.TS_SYNC
                for i in range(4)
            )
        ):
            break
        sync_offset = payload.find(bytes([protocol.TS_SYNC]), sync_offset + 1)

    if sync_offset < 0:
        return b"", last_seq, True

    ts_data = payload[sync_offset:]
    complete_len = len(ts_data) - len(ts_data) % protocol.TS_PKT_SIZE
    if complete_len == 0:
        return b"", last_seq, True

    return ts_data[:complete_len], last_seq, False
