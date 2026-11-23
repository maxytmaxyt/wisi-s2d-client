# Research – WISI OR S2D

Dokumentation, Analysematerial und verifizierte Erkenntnisse zum WISI OR S2D DVB-S2 Dongle.

## Struktur

| Pfad | Inhalt |
|---|---|
| [`docs/`](docs/) | Markdown-Dokumentation (`DETAILS.md`, `PROTOCOL.md`, `stream.md`, `pcap_analysis.md`, `AGENTS.md`, `SUMMARY.md`, APK-/Firmware-Analysen) |
| [`scripts/`](scripts/) | Analyse-Skripte (`find_*.py`, `parse_*.py`, `inspect_*.py`, …) – Arbeitsartefakte, nicht Teil des Clients |
| [`assets/`](assets/) | Binärartefakte: PCAPs, APK, Quellcode-ZIP |
| [`archive/`](archive/) | Veraltete Dokumente, Legacy-Prototypen und Rohberichte |

## Maßgebliche Dokumente

- **[`docs/DETAILS.md`](docs/DETAILS.md)** – Protokoll, Hardware, Opcodes, Link-Verschlüsselung – zuerst lesen
- **[`docs/stream.md`](docs/stream.md)** – Streaming-Ablauf Schritt für Schritt A–Z
- **[`docs/PROTOCOL.md`](docs/PROTOCOL.md)** – APIX-Befehlsreferenz (alle Opcodes)

## Mitschnitte (PCAPs)

| Datei | Inhalt |
|---|---|
| `assets/capture_pcapdroid_2026-10-11.pcap` | 200× `0xF9/0x0A`-Anfragen + EPG-Abfragen (`0xF6/0x30+0x31`, `0x32+0x33`, `0x35+0x36`) |
| `assets/PCAPdroid_12_Okt._16_16_04.pcap` | Kanallisten-Abruf (TCP `0xF6/0x20+0x21+0x22`), 440 Kanäle (`61.348 Bytes` XML) |
| `assets/PCAPdroid_12_Okt._16_28_17.pcap` | Vollständiger Tune-Ablauf (`0xF6/0x03`), UDP-Stream-Pulls (`0xF9/0x01`, 48.205 B fragmentiert) und Stream-Stop (`0xF8/0x07`) |

```bash
# Mitschnitte analysieren:
python src/wisi_s2d/cli/main.py --pcap "research/assets/PCAPdroid_12_Okt._16_16_04.pcap"
python src/wisi_s2d/cli/main.py --pcap "research/assets/PCAPdroid_12_Okt._16_28_17.pcap"
python src/wisi_s2d/cli/main.py --pcap "research/assets/capture_pcapdroid_2026-10-11.pcap"
```

## Analyse-Skripte

Der Ordner `scripts/` enthält zahlreiche Python-Skripte (`find_*.py`, `parse_*.py`, `inspect_*.py`, …) zur statischen APK-/DEX-Analyse und PCAP-Auswertung. Sie sind Arbeitsartefakte der Reverse-Engineering-Phase und nicht Teil des lauffähigen Clients (`src/`).

> `research/archive/` enthält historische Hypothesen und Legacy-Prototypen und darf nicht als Implementierungsgrundlage genutzt werden (siehe `research/archive/README.md`).
