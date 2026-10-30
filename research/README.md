# Research – WISI OR S2D

Dokumentation, Analysematerial und Erkenntnisse zum WISI OR S2D DVB-S2 Dongle.

## Struktur

| Pfad | Inhalt |
|---|---|
| [`DETAILS.md`](DETAILS.md) | Vollständige technische Referenz (Protokoll, Hardware, Opcodes, CAS) |
| [`stream.md`](stream.md) | Detaillierter Streaming-Ablauf A–Z |
| [`AGENTS.md`](AGENTS.md) | Hinweise und Orientierung für KI-Agenten |
| [`pcap_analysis.md`](pcap_analysis.md) | Rohe PCAP-Zählungen und Paketstatistiken |
| [`apk_reverse_engineering.md`](apk_reverse_engineering.md) | Statische APK-Analyse (Androguard, DEX, Native Libs) |
| [`apk-erkenntnisse-18.10.26.md`](apk-erkenntnisse-18.10.26.md) | Detaillierte Opcode-Tabelle aus SDK-Dekompilierung |
| [`assets/`](assets/) | Binärartefakte: PCAPs, APK, Quellcode-ZIP |
| [`archive/`](archive/) | Veraltete Dokumente und Legacy-Experimente |

## Maßgebliche Dokumente

- **[`DETAILS.md`](DETAILS.md)** – Protokoll, Hardware, Opcodes, CAS – zuerst lesen
- **[`stream.md`](stream.md)** – Streaming-Ablauf Schritt für Schritt A–Z

## Mitschnitte (PCAPs)

| Datei | Inhalt |
|---|---|
| `assets/capture_pcapdroid_2026-10-11.pcap` | 200× `0xF9/0x0A`-Anfragen + 198 Geräteantworten à 32.740 B |
| `assets/PCAPdroid_12_Okt._16_16_04.pcap` | Kanallisten-Abruf (TCP `0xF6/0x20+0x21`), 440 Kanäle |
| `assets/PCAPdroid_12_Okt._16_28_17.pcap` | Tune-Ablauf + UDP-Stream-Start |

```bash
# Mitschnitte analysieren:
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_16_04.pcap"
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_28_17.pcap"
python src/wisi/wisi.py --pcap "research/assets/capture_pcapdroid_2026-10-11.pcap"
```
