# Research – WISI OR S2D

Analysematerial und Erkenntnisse zum WISI OR S2D DVB-S2 Dongle.

## Struktur

| Pfad | Inhalt |
|---|---|
| [`assets/`](assets/) | Binärartefakte: PCAPs, APK, Quellcode-ZIP |
| [`outdated/`](outdated/) | Veraltete Dokumente (durch `DETAILS.md` ersetzt) |
| [`pcap_analysis.md`](pcap_analysis.md) | Rohe PCAP-Zählungen und Paketstatistiken |
| [`apk_reverse_engineering.md`](apk_reverse_engineering.md) | Statische APK-Analyse (Androguard, DEX, Native Libs) |
| [`apk-erkenntnisse-18.10.26.md`](apk-erkenntnisse-18.10.26.md) | Detaillierte Opcode-Tabelle aus SDK-Dekompilierung |

## Maßgebliche Dokumente

Die aktuellen, verifizierten Erkenntnisse sind im Root des Repos:

- **[`DETAILS.md`](../DETAILS.md)** – Vollständige technische Referenz (Protokoll, Hardware, Opcodes, CAS)
- **[`stream.md`](../stream.md)** – Detaillierter Streaming-Ablauf A–Z
