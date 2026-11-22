# WISI OR S2D / TiViCon Firmware- & Cloud-Architektur
*Dokumentation der Erkenntnisse aus Reverse Engineering der APK, des APIX-Protokolls, der nativen Bibliothek `libsecure_module.so` und der TiViCon Cloud-Schnittstelle.*

---

## 1. Hardware- & Gerätedaten des Dongles

Über die bestätigte APIX-3-Stufen-Abfrage (`0xFA/0x00`, `0xFA/0x07`, `0xFA/0x08`) und die Hersteller-Datenblätter ermittelte Realdaten:

* **Modell:** `OR S2D` (WISI / TiViCon OEM, baugleich mit **Schwaiger DSRD0100**)
* **SoC / Plattform:** ALi (Acer Laboratories Inc.) DVB-SoC (M35xx / M37xx Serie), 32-bit RISC CPU (650 MHz)
* **Arbeitsspeicher:** 128 MB DDR SDRAM
* **Flash-Speicher:** 8 MB SPI NOR Flash (Winbond W25Q64 o. ä.)
* **Tuner-Typ:** `26` (DVB-S2 Satellite, 950–2150 MHz, DiSEqC 1.0 & 1.2)
* **Customer-ID:** `6174` (`0x181E` – WISI OEM Kennung)
* **Hardware-Version:** `0` (Der Dongle meldet nativ `0`)
* **Software-Version:** `256` (`v1.0 / 0x0100`)
* **Loader-Version:** `255`
* **SVN-Revision:** `765789439`
* **CAS-Typ:** `65283` (`0xFF03`)
* **Chip-ID:** `9000000035a2a52b`
* **Seriennummer:** `84fd3834ea66`
* **MAC-Adresse:** `00:25:ff:01:01:03`
* **Netzwerk-Ports:** TCP `8802` (APIX Control), UDP `8800` (MPEG-TS Video Payload)
* **Physische Anschlüsse:**
  * 1x F-Buchse (Satellitenantenne LNB 13V/18V)
  * 1x RJ45 Fast Ethernet (100 Mbit/s)
  * 1x DC Hohlsteckerbuchse (12V / 5V Netzteil)
  * 1x USB-C Buchse (Laut WISI Datenblatt explizit für **"PC / Firmware-Updates"**)

---

## 2. TiViCon Cloud- & Update-Infrastruktur

### 2.1 Server-Endpunkte & URLs
* **WMS Basis-URL:** `https://wms.tiviconsolutions.com/api/`
* **CDMS Basis-URL:** `https://cdms.tiviconsolutions.com/api/`
* **Firmware-Speicherpfad:** `https://wms.tiviconsolutions.com/storage/uploads/fw_updates/`
* **Kanalisten-Speicherpfad:** `https://wms.tiviconsolutions.com/storage/uploads/upd_updates/`
* **Entwickler-Testserver (aus APK):** `http://192.168.2.80:8080/update.ini`

### 2.2 Geheime API-Schlüssel (Hardcoded im SDK)
* **Primärer WMS/CDMS API-Key:**
  `NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB`
* **Sekundärer API-Key:**
  `QhC6rpwfYIe7TlMTNDnoArEkWy3vXlGRvjnoGjXiy7RIWBQBwpj4t9yGlPZ8`

### 2.3 Update-Prüfung (`POST updater/updates/upd`)
* **Header:**
  * `Content-Type: application/json`
  * `Accept: application/json`
  * `X-Api-Key: NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB`
* **Payload:**
  ```json
  {
    "dongle_sw_version": "256",
    "dongle_hw_type": "0",
    "dongle_customer_id": 6174,
    "dongle_chip_id": "9000000035a2a52b",
    "updateType": "release"
  }
  ```
* **Antwort des Servers bei aktuellem Stand (Live getestet):**
  ```json
  {
    "status": "NO_UPDATE",
    "url": null,
    "filesize": null,
    "md5sum": null,
    "change_log": null
  }
  ```

---

## 3. Flash-Speicherlayout & `.abs`-Struktur

Aus dem dekompilierten SDK und der nativen Bibliothek `libsecure_module.so` (`SecureNativeModule.chunkGetName`):

* **Gesamtgröße:** 8.388.608 Byte (8 MB SPI Flash)
* **Bootloader (Offset `0x000000` - `0x03FFFF`):** Exakt 262.144 Byte (256 KB). Startet die ALi CPU, initialisiert DDR-RAM und liest die Chunk-Tabelle ein.
* **Chunk-Tabelle & Maincode (Offset `0x040000`):**
  * `libsecure_module.so` implementiert:
    * `chunk_init`
    * `chunk_goto`
    * `chunk_count`
    * `get_chunk_list`
    * `get_chunk_header_by_addr`
    * `chunk_check_single_crc`
    * `chunk_check_crc`
    * `chunk_id_check`
  * Format der Chunk-Header:
    * `data_id` (4 Byte): Chunk-Typ
    * `data_len` (4 Byte): Nutzdatenlänge
    * `data_off` (4 Byte): Flash-Offset
    * `data_crc` (4 Byte): CRC32
  * **Typische ALi Chunks:**
    * Bootloader (`0x01FF0100`)
    * Maincode OS + DVB Daemon (`0x02FD0100`, LZMA komprimiert)
    * Radioback / Seeback Menügrafiken (`0x03FC0100`)
    * Default Database `ddf` (`0x04FB0100`)
    * User Database `udf` (`0x05FA0100`)

---

## 4. Vollständige Befehlsreferenz: APIX Klasse `0xFA`

Die Klasse `0xFA` im 31-Byte USBC-Transport steuert Hardware-Infos, CAS-SAC und das Flashing:

| Opcode | Richtung | Länge | Funktion / SDK-Methode | Beschreibung |
|---|---|---|---|---|
| `0xFA / 0x00` | In ($\leftarrow$) | 64 B | `cmd_dongle_info_phase1` | Basis-Info: Tuner, SW, HW, Loader, Chip-ID, Serial |
| `0xFA / 0x01` | In ($\leftarrow$) | 6 B | `CreNovaDongleInitListener()` | Status-/CAS-Abfrage (Antwort: `fa 01 00 00 00 00`) |
| `0xFA / 0x02` | In ($\leftarrow$) | var | `CreNovaDongleInitListener(int i)` | Variabler Datenabruf |
| `0xFA / 0x03` | Out ($\rightarrow$) | var | `ccEmbedSacMessage` | Secure Authenticated Channel (SAC) Message |
| `0xFA / 0x04` | Out ($\rightarrow$) | 8 B Payload | `CMD_UPDATE_DONGLE_START` | Initialisierung Firmware-Update: `[TotalSize (4B), ChunkSize (4B)]` |
| `0xFA / 0x05` | Out ($\rightarrow$) | var | `CMD_UPDATE_DONGLE_DATA` | Firmware-Block: `[BlockIdx (2B), TotalBlocks (2B), Len (4B), Data...]` |
| `0xFA / 0x06` | In ($\leftarrow$) | 8 B | `CMD_UPDATE_DONGLE_STATUS` | Flashing-Fortschritt & Status (0–100 %) |
| `0xFA / 0x07` | In ($\leftarrow$) | 51 B | `cmd_dongle_info_phase2` | Modellname, SVN-Revision, VSC-ID |
| `0xFA / 0x08` | In ($\leftarrow$) | 480 B | `cmd_dongle_info_phase3` | MAC, Dongle-IP, Client-IP, Feature-Flags |
| `0xFA / 0x0A` | Out ($\rightarrow$) | 2 B | - | Steuerbefehl Parameter |
| `0xFA / 0x0B` | In ($\leftarrow$) | 4 B | - | Rückmeldung 4 Byte Status |
| `0xFA / 0x0C` | Out ($\rightarrow$) | 10 B | `forceTune` | Frequenz-, Tuner- und Suchlauf-Parameter |
| `0xFA / 0x0D` | In ($\leftarrow$) | 8 B | - | Tuner-/Lock-Status |
| `0xFA / 0x0E` | In ($\leftarrow$) | 6 B | - | Statusblock |
| `0xFA / 0x0F` | In ($\leftarrow$) | var | - | Datenübertragung |
| `0xFA / 0x10` | In ($\leftarrow$) | 6 B | - | DLE Handshake |
| `0xFA / 0x11` | In ($\leftarrow$) | var | - | Datentransfer |
| `0xFA / 0x12` | In ($\leftarrow$) | 52 B | - | Hardware-Parameterblock |
| `0xFA / 0x14` | In ($\leftarrow$) | 24 B | - | Statusmeldung |
| `0xFA / 0x18` | In ($\leftarrow$) | 6 B | - | CAN Status |
| `0xFA / 0x19` | In ($\leftarrow$) | var | - | Blocklese-Status |

---

## 5. Firmware-Update Flashing-Ablauf im Detail

Aus `onDongleCommunicationStatusHelpText.java` (Decompiliert aus SDK):
1. **Puffer-Chunking:**
   * Die Datei wird in Blöcke von bis zu `262.144 Byte` (256 KB) eingeteilt.
2. **Start-Kommando (`0xFA/0x04`):**
   * Host sendet Gesamtdateigröße und Chunk-Größe.
3. **Datenübertragung (`0xFA/0x05`):**
   * Header: `BlockIndex (16-bit BE)`, `TotalBlocks (16-bit BE)`, `ChunkLength (32-bit BE)`.
   * Payload: Rohdaten des Firmware-Blocks.
4. **Verifikation (`0xFA/0x06`):**
   * Der Dongle schreibt den Block in den SPI-NOR-Flash und quittiert den Vorgang.
5. **Reboot:**
   * Nach erfolgreichem Flash startet der Dongle neu.

---

## 6. Netzwerk- & Port-Scan-Ergebnisse (Live Dongle 192.168.178.32)

* **Offene Ports:** Ausschließlich Port `8802` TCP (APIX) und Port `8800` UDP (MPEG-TS).
* **Geschlossene Standard-Dienste:** Port 21 (FTP), 22 (SSH), 23 (Telnet), 80/8080 (HTTP), 554 (RTSP / SAT>IP).
* **Ergebnis:** Es gibt über das TCP/IP-Netzwerk keine Debug-Shell und keinen Befehl zum Auslesen des Flash-Speichers. Das Flashen (`0xFA/0x04..0x06`) ist eine reine Einweg-Schreiboperation.
