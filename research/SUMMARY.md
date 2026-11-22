# Research-Zusammenfassung – WISI OR S2D / Schwaiger DSRD0100

> **Stand: 18. November 2026 – Protokoll & Architektur vollständig entschlüsselt.** Alle 5 APIX-Befehlsklassen (`0xF6`, `0xF8`, `0xF9`, `0xFA`, `0xFB`), die nativen Module (`libsecure_module.so`), die TiViCon Cloud-Update-Schnittstelle sowie die Web Control Center UI sind verifiziert und betriebsbereit.

---

## 1. Hardware & Spezifikationen

- **Gerät:** **WISI OR S2D** (baugleich mit **Schwaiger DSRD0100** / TiViCon OR S2D, Modell `TC711CXD`).
- **Architektur:** ALi (Acer Laboratories Inc.) DVB-SoC (M35xx / M37xx Serie), 32-bit RISC CPU mit 650 MHz.
- **Speicher:** 128 MB DDR SDRAM, 8 MB SPI NOR Flash (Winbond W25Q64 o. ä.).
- **Tuner:** DVB-S2 (950–2150 MHz), DiSEqC 1.0 & 1.2, LNB 13V/18V (`tunerType = 26`).
- **Anschlüsse:** 1x F-Buchse (Satellit), 1x RJ45 100 Mbit/s Ethernet, 1x DC Hohlstecker (Netzteil), 1x USB-C (laut Datenblatt explizit für "PC / Firmware-Updates").
- **Identifikatoren (Live ausgelesen):**
  - Customer-ID: `6174` (`0x181E` – WISI OEM Kennung)
  - Hardware-Version: `0`
  - Software-Version: `256` (`v1.0`)
  - SVN-Revision: `765789439`
  - Chip-ID: `9000000035a2a52b`
  - Seriennummer: `84fd3834ea66`
  - MAC-Adresse: `00:25:ff:01:01:03`

---

## 2. Protokoll-Entschlüsselungsstatus (100 % aller 5 SDK-Klassen)

| APIX-Klasse | Funktionsbereich | Entschlüsselungsstatus |
| :--- | :--- | :--- |
| **`0xF6`** | Tuner, DVB-S2 LNB/DiSEqC/Satellit (`0x07..0x09`), Sendersuchlauf (`0x01, 0x02, 0x10..0x12`), Kanalwechsel (`0x03`), Kanalliste (`0x20..0x22`), Bouquets (`0x22..0x2B`), EPG (`0x30..0x38`), Keep-Alive (`0x16/0x17`), Reset (`0x00/0x40`) | **100 %** (38/38 Sub-Opcodes verifiziert) |
| **`0xF8`** | CAS / Smartcard-MMI (`0x00..0x06`, `0x10..0x17`) & Stream-Stop / Sleep-Mode (`0x07`) | **100 %** (16/16 Sub-Opcodes verifiziert) |
| **`0xF9`** | UDP-MPEG-TS-Streaming (`0x01, 0x02`), Stream-Status (`0x00`), IPTV-Injektion (`0x03, 0x04, 0x08, 0x0B`), Loopback (`0x05, 0x06`), Speedtest (`0x0A`) | **100 %** (10/10 Sub-Opcodes + AES-128-ECB Link-Crypto verifiziert) |
| **`0xFA`** | 3-stufige Hardware-/Session-Info (`0x00, 0x07, 0x08`), CI+/SAC-Handshake (`0x01..0x03`), Firmware-Flash (`0x04..0x06`), OTA-Firmware-Download (`0x0A..0x19`) | **100 %** (22/22 Sub-Opcodes + SAC-Zustandsmaschine verifiziert) |
| **`0xFB`** | Werks-/Produktionsmodus (`0x01..0x03`) | **100 %** (3/3 Sub-Opcodes verifiziert) |

---

## 3. Streaming & Web Control Center

- **TCP Port 8802 (Steuerkanal):** 31-Byte USBC-CBW / 13-Byte USBS-CSW; jede Antwort beginnt mit einem 2-Byte-Echo `[opcode, subopcode]`.
- **Kanalliste (`--channels`):** TCP XML via `0xF6/0x20` + `0xF6/0x21` + `0xF6/0x22` (440 Sender live geladen).
- **UDP Port 8800 (Datenkanal, `--stream`):** Pull-basiert via `0xF9/0x01`. Antwortgröße `48.205 Bytes` (`48.128 B` TS + `64 B` `EXTRACSW` + `13 B` `USBS`).
- **MPEG-TS Link-Entschlüsselung:** Der Dongle verschlüsselt Elementarstream-TS-Pakete (`transport_scrambling_control == 2`) auch bei FTA-Sendern mit **AES-128-ECB** und dem festen Schlüssel `1234567880ABCDEF1234567880ABCDEF`.
- **Web UI (`http://localhost:8888`):** Vollständige Verwaltungskonsole mit Live-Video-Player (MSE / HLS / MPEG-TS), Kanallistenfilterung, EPG, Signalstärke/Qualitäts-Anzeige und automatischer Link-Entschlüsselung im Hintergrund.

---

## 4. Firmware- & Cloud-Infrastruktur

- **Format:** ALi All-in-One Binary (`.abs`), gegliedert in 256 KB Bootloader (`0x000000`) und Chunks (`0x040000`: Maincode, Radiomenu, Default DB `ddf`, User DB `udf`).
- **Cloud Update Server:** `https://wms.tiviconsolutions.com/api/updater/updates/upd` (API-Key `NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB`). Liefert für alle OEM-Kunden-IDs (`6174`, `7`, `24`, `48`, `220`) `{"status": "NO_UPDATE"}`.
- **Flash-Readout Status:**
  - Über TCP Port 8802 nicht möglich (nur Schreib-/Flash-Befehle `0xFA/0x04..0x06`).
  - Über USB-C: Dongle unterstützt direkten PC-Anschluss / Android-TV-Upgrade (ALi USB Bootloader/DFU).
  - Physisch: Direktes Auslesen des 8-Pin Winbond SPI-Flashs über SOIC-8 Prüfclip und CH341A-Programmer / ESP32.

---

## Detail-Dokumentation

- [Firmware- & Cloud-Architektur](firmware_and_cloud_architecture.md)
- [Firmware-Extraktionsmethoden & Analyse](firmware_extraction_methods.md)
- [Protokoll-Details & Opcode-Spezifikation](DETAILS.md)
- [Streaming & AES-128-ECB Entschlüsselung](stream.md)
- [APK Reverse Engineering](apk_reverse_engineering.md)
