# Research-Zusammenfassung – WISI OR S2D

> **Stand: November 2026 – Protokoll zu 100 % entschlüsselt.** Alle 5 APIX-Befehlsklassen (`0xF6`, `0xF8`, `0xF9`, `0xFA`, `0xFB`) sind aus dem dekompilierten APK-Quellcode (`com.crenova.tv.dongle.dvb.sdk.*`), `libsecure_module.so`, PCAP-Mitschnitten und durch Live-Tests gegen den echten WISI OR S2D Dongle (`192.168.178.32`) vollständig verifiziert.

## Protokoll-Entschlüsselungsstatus (100 % aller 5 SDK-Klassen)

| APIX-Klasse | Funktionsbereich | Entschlüsselungsstatus |
| :--- | :--- | :--- |
| **`0xF6`** | Tuner, DVB-S2 LNB/DiSEqC/Satellit (`0x07..0x09`), Sendersuchlauf (`0x01, 0x02, 0x10..0x12`), Kanalwechsel (`0x03`), Kanalliste (`0x20..0x22`), Bouquets (`0x22..0x2B`), EPG (`0x30..0x38`), Keep-Alive (`0x16/0x17`), Reset (`0x00/0x40`) | **100 %** (38/38 Sub-Opcodes verifiziert) |
| **`0xF8`** | CAS / Smartcard-MMI (`0x00..0x06`, `0x10..0x17`) & Stream-Stop / Sleep-Mode (`0x07`) | **100 %** (16/16 Sub-Opcodes verifiziert) |
| **`0xF9`** | UDP-MPEG-TS-Streaming (`0x01, 0x02`), Stream-Status (`0x00`), IPTV-Injektion (`0x03, 0x04, 0x08, 0x0B`), Loopback (`0x05, 0x06`), Speedtest (`0x0A`) | **100 %** (10/10 Sub-Opcodes + AES-128-ECB Link-Crypto verifiziert) |
| **`0xFA`** | 3-stufige Hardware-/Session-Info (`0x00, 0x07, 0x08`), CI+/SAC-Handshake (`0x01..0x03`), Firmware-Flash (`0x04..0x06`), OTA-Firmware-Download (`0x0A..0x19`) | **100 %** (22/22 Sub-Opcodes + SAC-Zustandsmaschine verifiziert) |
| **`0xFB`** | Werks-/Produktionsmodus (`0x01..0x03`) | **100 %** (3/3 Sub-Opcodes verifiziert) |

## Wichtigste Erkenntnisse & Live-Betrieb

- **Gerät:** **WISI OR S2D** (OEM: TiViCon OR S2D / Schwaiger DSRD0100, Modell `TC711CXD`, `tunerType = 26`, `usbProtocolVersion = 2`).
- **TCP Port 8802 (Steuerkanal):** 31-Byte USBC-CBW / 13-Byte USBS-CSW; jede Antwort beginnt mit einem 2-Byte-Echo `[opcode, subopcode]`.
- **Kanalliste (`--channels`):** TCP XML via `0xF6/0x20` + `0xF6/0x21` + `0xF6/0x22` (440 Sender live geladen). **`prog_idx = 0x40xxxxxx` = TV (`type="TV"`), `0x48xxxxxx` = Radio (`type="RD"`)**; Verschlüsselung wird allein durch `fta="0"` angezeigt.
- **EPG (`--epg`):** TCP XML via `0xF6/0x30` + `0xF6/0x31` mit `prog_idx` an USBC-Bytes 25–28.
- **Kanalwechsel (`0xF6/0x03`):** Modus `0x00000002` an USBC-Bytes 21–24 und `prog_idx` an Bytes 25–28 (`ACTION_CHANGE_CHANNEL_BY_PROGIDX`).
- **DVB-S2 Sendersuchlauf (`src/scan.py`):** 7-stufige Sequenz über `0xF6/0x07` (LNB) → `0xF6/0x08` (DiSEqC) → `0xF6/0x09` (Satellit) → `0xF6/0x01` (Transponder, `data_len=32`) → `0xF6/0x10` (Scan Start) → `0xF6/0x02` (17-Byte Fortschrittspoll) → `0xF6/0x11 + 0x12` (Suchlauf-XML).
- **UDP Port 8800 (Datenkanal, `--stream`):** Pull-basiert via `0xF9/0x01` (`byte21=0x00` beim ersten Block und nach jedem erfolgreichen Block; `byte21=0x01` nur bei Retry nach Timeout); Antwortgröße `48.205 Bytes` (`48.128 B` TS + `64 B` `EXTRACSW` mit Sequenznummer in Byte 12 + `13 B` `USBS`).
- **Link-Verschlüsselung der TS-Pakete (`--decrypt` / `--decrypt-ts`):** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`transport_scrambling_control == 2`) auch bei FTA-Sendern mit **AES-128-ECB (`AES/ECB/NoPadding`)** und dem statischen Schlüssel `1234567880ABCDEF1234567880ABCDEF`.
- **CI+ / SAC-Handshake (`0xFA/0x01..0x03`, `libsecure_module.so`):** 3-stufiger Diffie-Hellman-/SAC-Schlüsselaustausch (Root-Seed `LukeRanDolphCI+1`) über `0xFA/0x03` (Write) → `0xFA/0x01` (Poll Len) → `0xFA/0x02` (Read); auf FTA-Firmware (`clearFTAStream == 1` in `0xFA/0x08`) überspringt das SDK den SAC-Handshake komplett.

## Vollständige Referenz
→ [`DETAILS.md`](DETAILS.md), [`stream.md`](stream.md) und [`apk_reverse_engineering.md`](apk_reverse_engineering.md)
