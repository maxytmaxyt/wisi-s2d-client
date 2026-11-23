# Research – WISI OR S2D

Dokumentation, Analysematerial und verifizierte Erkenntnisse zum WISI OR S2D DVB-S2 Dongle.

## Struktur

| Pfad | Inhalt |
|---|---|
| [`DETAILS.md`](DETAILS.md) | Vollständige technische Referenz (Protokoll, Hardware, Opcodes, Link-Verschlüsselung & CAS) |
| [`PROTOCOL.md`](PROTOCOL.md) | APIX-Befehlsreferenz (alle Opcodes und Paketstrukturen) |
| [`stream.md`](stream.md) | Verifizierter Streaming-Ablauf A–Z (inkl. AES-128-ECB-Link-Entschlüsselung) |
| [`pcap_analysis.md`](pcap_analysis.md) | PCAP-Auswertung und Paketstatistiken |
| [`apk_reverse_engineering.md`](apk_reverse_engineering.md) | Statische APK-Analyse (DEX, Native Libs, CryptoManager) |
| [`apk-erkenntnisse-18.10.26.md`](apk-erkenntnisse-18.10.26.md) | Detaillierte UDP-Opcode- und Pufferanalyse aus dem SDK |
| [`firmware_and_cloud_architecture.md`](firmware_and_cloud_architecture.md) | Firmware- und Cloud-Architektur |
| [`firmware_extraction_methods.md`](firmware_extraction_methods.md) | Methoden zur Firmware-Extraktion |
| [`AGENTS.md`](AGENTS.md) | Hinweise, Modulübersicht und Protokoll-Checkliste für KI-Agenten |
| [`SUMMARY.md`](SUMMARY.md) | Kurzfassung der verifizierten Ergebnisse |
| [`assets/`](assets/) | Binärartefakte: PCAPs, APK, Quellcode-ZIP |
| [`archive/`](archive/) | Veraltete Dokumente, Legacy-Prototypen und Rohberichte |

## Maßgebliche Dokumente

- **[`DETAILS.md`](DETAILS.md)** – Protokoll, Hardware, Opcodes, Link-Verschlüsselung – zuerst lesen
- **[`stream.md`](stream.md)** – Streaming-Ablauf Schritt für Schritt A–Z
- **[`PROTOCOL.md`](PROTOCOL.md)** – APIX-Befehlsreferenz (alle Opcodes)

## Mitschnitte (PCAPs)

| Datei | Inhalt |
|---|---|
| `assets/capture_pcapdroid_2026-10-11.pcap` | 200× `0xF9/0x0A`-Anfragen + EPG-Abfragen (`0xF6/0x30+0x31`, `0x32+0x33`, `0x35+0x36`) |
| `assets/PCAPdroid_12_Okt._16_16_04.pcap` | Kanallisten-Abruf (TCP `0xF6/0x20+0x21+0x22`), 440 Kanäle (`61.348 Bytes` XML) |
| `assets/PCAPdroid_12_Okt._16_28_17.pcap` | Vollständiger Tune-Ablauf (`0xF6/0x03`), UDP-Stream-Pulls (`0xF9/0x01`, 48.205 B fragmentiert) und Stream-Stop (`0xF8/0x07`) |

```bash
# Mitschnitte analysieren:
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_16_04.pcap"
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_28_17.pcap"
python src/wisi/wisi.py --pcap "research/assets/capture_pcapdroid_2026-10-11.pcap"
```

## Analyse-Skripte

Der Ordner enthält zahlreiche Python-Skripte (`find_*.py`, `parse_*.py`, `inspect_*.py`, …) zur statischen APK-/DEX-Analyse und PCAP-Auswertung. Sie sind Arbeitsartefakte der Reverse-Engineering-Phase und nicht Teil des lauffähigen Clients (`src/`).

> `research/archive/` enthält historische Hypothesen und Legacy-Prototypen und darf nicht als Implementierungsgrundlage genutzt werden (siehe `research/archive/README.md`).
