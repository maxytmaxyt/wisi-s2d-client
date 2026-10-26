# Research-Zusammenfassung – WISI OR S2D

> Stand: Oktober 2026. Nur verifizierte Erkenntnisse aus PCAP-Analyse und APK-Dekompilierung.

## Was bestätigt ist

### Gerät
- **WISI OR S2D** (OEM: TiViCon OR S2D / Schwaiger DSRD0100)
- Nicht zu verwechseln mit dem älteren O2D / Tivizen

### Protokoll
- TCP Port 8802 (Steuerkanal): 31-Byte USBC-CBW / 13-Byte USBS-CSW
- UDP Port 8800 (Datenkanal): Pull-basiert via `0xF9/0x01`
- Kanalliste: TCP XML via `0xF6/0x20` + `0xF6/0x21`
- `0xF9/0x0A` = Speedtest (kein Kanal-DB!)

### APK-Quellen
- `com.tivicon.tv2smart.mobile` v`3.M20260803.0-rev-a14aeb377`
- Analyse: [`apk_reverse_engineering.md`](apk_reverse_engineering.md), [`apk-erkenntnisse-18.10.26.md`](apk-erkenntnisse-18.10.26.md)

### PCAPs
- 3 Mitschnitte in [`assets/`](assets/) – Details in [`pcap_analysis.md`](pcap_analysis.md)

## Vollständige Referenz
→ [`DETAILS.md`](../DETAILS.md) und [`stream.md`](../stream.md)
