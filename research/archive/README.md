# Archive – Veraltete Dokumente und Legacy-Code

Dieser Ordner enthält ältere Analysen und frühe Implementierungsversuche, die durch neuere Erkenntnisse überholt wurden. **Nicht als Implementierungsgrundlage nutzen.**

## Inhalt

| Datei | Inhalt | Status |
|---|---|---|
| [`SUMMARY.md`](SUMMARY.md) | Kompakte Zusammenfassung älterer Erkenntnisse | ⚠️ veraltet – durch `research/DETAILS.md` ersetzt |
| [`or_s2d_protocol_analysis.md`](or_s2d_protocol_analysis.md) | Früher Befehlsablauf aus PCAPs vom 12. Oktober | ⚠️ veraltet – durch `research/DETAILS.md` ersetzt |
| [`neue_erkenntnisse.md`](neue_erkenntnisse.md) | Hypothesen aus Spec-Matching; teils überholt | ⚠️ veraltet |
| [`or_s2d_firmware_update.md`](or_s2d_firmware_update.md) | Firmware-Update-Wege laut WISI-Datenblatt | ✅ noch gültig, aber nicht aktiv relevant |
| [`protocol_spec_or_s2d.md`](protocol_spec_or_s2d.md) | Breite Systemhypothesen; HTTP/REST/USB-Details nicht bestätigt | ⚠️ Ideenquelle, kein Implementierungsbeleg |
| [`apk-report-com.tivicon.tv2smart.mobile.txt`](apk-report-com.tivicon.tv2smart.mobile.txt) | Roher APK-Analysebericht | ⚠️ Rohdaten – Auswertung in `research/apk_reverse_engineering.md` |
| [`wisi_dongle_client.py`](wisi_dongle_client.py) | Erster Prototyp-Client | ⚠️ Legacy – durch `src/` ersetzt |
| [`wisi_dongle_simple.py`](wisi_dongle_simple.py) | Vereinfachter Prototyp | ⚠️ Legacy – durch `src/` ersetzt |
| [`wisi_dongle_v1.py`](wisi_dongle_v1.py) | Version 1 des Clients | ⚠️ Legacy – durch `src/` ersetzt |

## Aktuelle Referenzen

Für aktuelle und verifizierte Informationen:

- **[`../DETAILS.md`](../DETAILS.md)** – technische Referenz
- **[`../stream.md`](../stream.md)** – Streaming-Ablauf
- **[`../../src/`](../../src/)** – aktueller Quellcode
