# Research-Zusammenfassung – WISI OR S2D

> Stand: November 2026. Alle Punkte sind gegen PCAP-Mitschnitte, den dekompilierten APK-Quellcode und live gegen den echten WISI OR S2D Dongle (`192.168.178.32`) verifiziert.

## Was bestätigt und live getestet ist

### Gerät
- **WISI OR S2D** (OEM: TiViCon OR S2D / Schwaiger DSRD0100)
- Nicht zu verwechseln mit dem älteren O2D / Tivizen

### Protokoll & Live-Betrieb
- **TCP Port 8802 (Steuerkanal):** 31-Byte USBC-CBW / 13-Byte USBS-CSW; jede Antwort beginnt mit einem 2-Byte-Echo `[opcode, subopcode]`
- **Kanalliste (`--channels`):** TCP XML via `0xF6/0x20` + `0xF6/0x21` + `0xF6/0x22` (440 Sender live geladen)
- **EPG (`--epg`):** TCP XML via `0xF6/0x30` + `0xF6/0x31` mit `prog_idx` an USBC-Bytes 25–28
- **Kanalwechsel (`0xF6/0x03`):** Modus `0x00000002` an USBC-Bytes 21–24 und `prog_idx` an Bytes 25–28 (`ACTION_CHANGE_CHANNEL_BY_PROGIDX`)
- **UDP Port 8800 (Datenkanal, `--stream`):** Pull-basiert via `0xF9/0x01` (`byte21=0x00` beim ersten Block und nach jedem erfolgreichen Block; `byte21=0x01` nur bei Retry nach Timeout); Antwortgröße `48.205 Bytes` (`48.128 B` TS + `64 B` `EXTRACSW` mit Sequenznummer in Byte 12 + `13 B` `USBS`)
- **Link-Verschlüsselung der TS-Pakete:** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`transport_scrambling_control == 2`) auch bei FTA-Sendern mit **AES-128-ECB (`AES/ECB/NoPadding`)** und dem statischen Schlüssel `1234567880ABCDEF1234567880ABCDEF`
- **Stream-Stop (`0xF8/0x07`):** 35-Byte-Befehl (`31 B` USBC + `01 00 00 00` Payload) beim Beenden des Streams
- **`0xF9/0x0A`:** Speedtest (`getSpeedTestMbps()`), keine Kanal-Datenbank

## Vollständige Referenz
→ [`DETAILS.md`](DETAILS.md) und [`stream.md`](stream.md)
