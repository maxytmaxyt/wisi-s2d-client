# Firmware-Extraktionsmethoden: WISI OR S2D / Schwaiger DSRD0100
*Analyse und Bewertung aller Software- und Hardware-Wege zur Beschaffung der `.abs`-Firmware.*

---

## 1. Übersicht & Zielsetzung

Ziel ist es, den binären Inhalt der Firmware des **WISI OR S2D** (baugleich mit **Schwaiger DSRD0100**) vollständig auszulesen oder zu beschaffen, um:
1. Den Bootloader und den komprimierten Maincode (Betriebssystem + TV2Smart-Daemon) zu analysieren.
2. Die Default-Transponder- und Kanaldatenbank (`ddf`) zu extrahieren.
3. Eventuell vorhandene Sicherheitszertifikate / Root-Keys zu sichern.
4. Langfristig eine modifizierte oder offene Firmware (z. B. echtes SAT>IP ohne App-Zwang) zu erstellen.

---

## 2. Firmware-Format: ALi All-in-One Binary (`.abs`)

Aus dem dekompilierten Quellcode des TV2Smart-SDK (`Utils.ZipFileFilter`, `SecureNativeModule.chunkGetName`) und der nativen Bibliothek `libsecure_module.so` geht der genaue Aufbau des Flash-Speichers hervor:

* **Gesamtgröße:** `8.388.608 Byte` (8 MB SPI-NOR-Flash, z. B. Winbond W25Q64).
* **Bootloader-Offset:** Offset `0x000000` bis `0x03FFFF` (exakt `262.144 Byte` = 256 KB).
* **Maincode & Chunk-Tabelle:** Beginnt bei Offset `0x040000` (`262.144`).
* **Chunk-Header-Format (aus `libsecure_module.so`):**
  * `data_id` (4 Byte): Chunk-Kennung (z. B. Bootloader, Maincode, Seeback, Default-DB, User-DB).
  * `data_len` (4 Byte): Chunk-Nutzdatenlänge.
  * `data_off` (4 Byte): Speicheradresse / Offset im Flash.
  * `data_crc` (4 Byte): CRC32-Prüfsumme.
* **Firmware-Identifikationsstring (15 Byte Rückgabe von `chunkGetName`):**
  * Bytes 0–7: 8 Hex-Zeichen Customer-ID (z. B. `0000181E` = 6174).
  * Byte 8: Trennzeichen.
  * Bytes 9–10: 2 Hex-Zeichen Software-Version (z. B. `01` = 256).
  * Byte 11: Trennzeichen.
  * Bytes 12–13: 2 Hex-Zeichen Hardware-Version.

---

## 3. Analyse der Software- & Web-Wege (Stand 27./28. November 2026)

### Methode 1: Cloud-Download über TiViCon WMS / HWMS / CDMS / HDMS API
* **Mechanismus:** Die offizielle TV2Smart-App sendet beim Start eine Update-Anfrage an:
  `POST https://wms.tiviconsolutions.com/api/updater/updates/upd`
  mit API-Key `NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB`.
* **Ergebnis der erweiterten Live-Prüfung (27.11.2026):**
  * **Beide Endpunkte (`wms` & `hwms`) & beide SDK-Keys (`NG6k...`, `QhC6...`)** getestet.
  * **Niedrigere/ältere Versionsstände simuliert:** `0`, `1`, `"0"`, `"1"`, `"0.1"`, `"0.0.1"`, `"0.1.0"`, `"1.0.0"`, `"100"`, `"200"`, `"255"`, `"256"`.
  * **`updateType`-Modi:** Sowohl `"release"` als auch das serverseitig gültige `"debug"` geprüft (**134** gedrosselte `debug`-Requests auf `wms` und `hwms`).
  * **`dongle_hw_type`-Varianten:** `"0"`, `"1"`, `"2"`, `"3"`, `"26"`, `"0x00"`, `"OR S2D"`, `"OR_S2D"`, `"ORS2D"`, `"WISI OR S2D"`, `"TC711"`, `"TC711CXD"`, `"DSRD0100"`, `"DVB-S2"`, `"ALI3510"`, `"ALI_M3510"`, `"M3510"`, `"S2D"`.
  * **Erweiterter Customer-ID-Sweep:** `6174` (WISI Live-Dongle, auch mit `chip_id`, `serial`, `mac`, `svn` sowie Hex-Varianten `181E`, `0000181E`, `0x181E`), `7` (Schwaiger DSRD0100), `24`, `48`, `220` sowie vollständig alle IDs **`0–260`** im gedrosselten Durchlauf (`267` Requests ohne HTTP `429` / Timeout) → **0 Treffer**, durchgehend `{"status":"NO_UPDATE","url":null,"filesize":null,"md5sum":null,"change_log":null}`.
  * **Geschützte `fw`-Routen:** `cdms.tiviconsolutions.com/api/updater/updates/fw` und `hdms.tiviconsolutions.com/api/updater/updates/fw` existieren als POST-Routen, blockieren beide App-Keys aber mit HTTP `401 {"message":"Unauthorized action"}` bzw. `404`.
  * **Storage-Direktpfade:** `/storage/uploads/fw_updates/` (und Dateinamen wie `6174.abs`, `OR_S2D.abs`, `TC711CXD.abs`, `update.ini`) sowie `/storage/uploads/upd_updates/` liefern auf `wms` und `cdms` HTTP `404`.
* **Fazit:** Auf der öffentlichen/App-seitigen TiViCon-Infrastruktur ist aktuell keine Firmware-Datei hinterlegt – auch nicht durch das Vortäuschen sehr alter Dongle-Versionen (`SW 0`/`1`) oder `updateType="debug"`.

---

### Methode 2: Extraktion aus APKs (Bundled Offline-Firmware)
* **Mechanismus:** Das SDK (`onDongleCommunicationStatusHelpText.java`) prüft den Ordner `assets/dongle-firmware/` auf `.abs`-Dateien, um Offline-Updates zu unterstützen.
* **Ergebnis:**
  * In `TV2Smart_3.M20260803.0` liegt in `assets/dongle-firmware/` lediglich die Platzhalterdatei `here_put_abs` (0 Byte).
  * **Verwandte TiViCon-/CreNova-Apps identifiziert:**
    * `com.tivicon.tv2smart.atv` (*TV2Smart Android TV*, laut Schwaiger-Handbuch für "Dongle USB Upgrade" genutzt)
    * `com.tivicon.tv2smart.mobile` (*TV2Smart Mobile*, z. B. `3.M20240221.0`, `3.M20251024.0`, `3.M20260803.0`, `3.M20261116.0`)
    * `com.crenova.tv.dongle` (*TiViCon Connect*, 2022) & `com.crenova.mobile.dongle` (*TiViCon Connect (MOBILE)*, 2022)
    * `com.crenova.tv.dongle.hospitality` (*TiViCon Hospitality*)
    * `com.tiviconplay.tv.dongle` / `com.tiviconplay.mobile.dongle` (*TiViConPlay*)
    * `com.cm.wisitvapp` (*WISI TV-APP*, 2017/2018) & `com.cm.tivicon` (*TiViCon*, 2016–2018)
  * **Archiv-Check (27.11.2026):** Über die Aptoide-API ist keines dieser Pakete gelistet (`404`); `d.apkpure.com` schützt seine XAPK/APK-Downloads per Cloudflare (`HTTP 403`).
* **Offener manueller Schritt:** Ältere ATV-/Connect-XAPKs über einen regulären Browser von APKPure laden und als ZIP auf `.abs`-Dateien in `assets/dongle-firmware/` prüfen.

---

### Methode 2b: Herstellerportale, Wayback Machine & Open-Source-Suche (Deep Research 27.11.2026)
* **WISI (`wisi.at`, `wisi.de`, `wisi.ch/download/`):** Auf den öffentlichen Downloadportalen liegen nur Updates für klassische Receiver (z. B. OR230S, OR181A/OR294, OR152F, OR397A), nichts zum `OR S2D`. Eine Support-E-Mail vom 18.10.2026 an `info@wisi.at` blieb unbeantwortet.
* **Schwaiger (`download.schwaiger.de` & `schwaiger.de/products/dsrd0100`):** Live-Abfrage des Download-Centers (`area=1` Konformität, `area=2` Produktunterlagen) nach `DSRD0100` / `DSRD` liefert ausschließlich `/storage/2/DSRD0100_Bedienungsanleitung_Deutsch.pdf` und `/datasheets/3643_Datenblatt.pdf` – keine Firmware-Archive.
* **Wayback Machine (`web.archive.org` CDX):** Abfragen auf `download.schwaiger.de/*`, `*.tivicon.com/*`, `*.tiviconsolutions.com/*` und `cdms.tiviconsolutions.com/*` liefern keine archivierten `.abs`- oder `.bin`-Dateien.
* **Open Source (`Rikku2000/soralink`):** C-Bridge für WISI/S2D und SAT>IP (`DIGIBIT Twin`) geprüft; bestätigt die lokale Protokoll- und AES-128-ECB-Implementierung, enthält aber keine Firmware-Dumps.

---

### Methode 3: Auslesen über Netzwerk (TCP Port 8802)
* **Mechanismus:** Prüfung, ob das APIX-Befehlsprotokoll über TCP Port 8802 einen Speicher- oder Flash-Lese-Befehl bereitstellt.
* **Ergebnis der Live-Prüfung:**
  * Portscan auf `192.168.178.32`: Nur Port 8802 (TCP) ist offen (kein SSH, Telnet, FTP, HTTP oder TFTP).
  * Die Befehlsklasse `0xFA` unterstützt ausschließlich das **Schreiben/Flashen**:
    * `0xFA/0x04` (`CMD_UPDATE_DONGLE_START`)
    * `0xFA/0x05` (`CMD_UPDATE_DONGLE_DATA`)
    * `0xFA/0x06` (`CMD_UPDATE_DONGLE_STATUS`)
  * Lesebefehle (`0xFA/0x00`, `0x07`, `0x08`) liefern nur strukturierte Statusblöcke (Seriennummer, Chip-ID, MAC, SVN), aber keinen Rohspeicherzugriff.
* **Fazit:** Ein direktes Auslesen des Flash-Speichers über das Netzwerk ist firmwareseitig nicht implementiert und somit über Port 8802 unmöglich.

---

### Methode 4: Auslesen über USB-C (PC / Firmware-Update-Port)
* **Mechanismus:** Laut offiziellem WISI-Datenblatt und Schwaiger-Bedienungsanleitung ist die USB-C-Buchse explizit für **"PC / Firmware-Updates"** vorgesehen.
* **Funktionsweise bei ALi DVB SoCs:**
  * ALi-Chipsätze (M35xx/M37xx) besitzen ein internes Boot-ROM.
  * Wenn der Dongle per USB-C an einen PC angeschlossen wird:
    * Standard-Modus: USB-CDC / Serial / Bulk-Interface für PC-Kommunikation (Hinweis aus Schwaiger-Anleitung: *„Die direkte Verbindung des Geräts mit dem Dongle über USB deaktiviert die Netzwerkfunktion“*).
    * Bootloader-/Recovery-Modus (z. B. durch Halten eines internen Tasters oder bei leerem Flash): Meldet sich als ALi USB Bootloader / DFU Device.
    * Tools wie *ALi Universal Upgrade Tool*, *ALi M35xx PC Tool* oder Open-Source-Treiber können über diesen Port Firmware auslesen oder flashen.
* **Status:** Noch nicht am USB-C-Port eines PCs getestet (VID/PID im direkten USB-Betrieb noch zu prüfen).

---

## 4. Hardware-Extraktion (Garantierter Fallback)

Falls kein Download verfügbar ist und kein USB-Lesezugriff besteht, ist das physische Auslesen der Standardweg:

1. **Gehäuse öffnen:** Der Dongle (65 × 65 × 20 mm) ist geklipst.
2. **Flash-Identifikation & Spannungsprüfung (kritisch!):**
   * 8-Pin SPI NOR Flash Chip (8 MB) auf der Platine identifizieren (z. B. Winbond `W25Q64JV` = **3,3 V**, vs. `W25Q64JW`/`FW` = **1,8 V**!).
   * **Achtung:** Niemals blind `3,3 V` an einen 1,8-V-Flash anlegen (Zerstörungsgefahr); vorab Chip-Aufdruck + Datenblatt prüfen.
3. **Auslesen mit SOIC-8 Clip (CH341A oder ESP32 NodeMCU-32S):**
   * Ein SOIC-8 Prüfclip wird auf den Chip gesetzt (ohne Löten); vor dem Einschalten Durchgang/Kurzschluss benachbarter Pins prüfen und **niemals gleichzeitig** das 12-V-Dongle-Netzteil einstecken.
   * **Variante A (empfohlen): CH341A USB-Programmer (3,3-V-modifiziert)** mit `flashrom -p ch341a_spi -r wisi_or_s2d_dump.bin`.
   * **Variante B: ESP32 NodeMCU-32S über VSPI (nur bei verifiziertem 3,3-V-Flash):**
     * *Interne ESP32-Flash-Pins `GPIO 6–11` sowie Strapping-Pin `GPIO 12` **nicht** verwenden!*
     * Pinbelegung SOIC-8 ↔ ESP32 VSPI:
       * Pin 1 (`/CS`) ↔ **`GPIO 5`**
       * Pin 2 (`DO` / MISO) ↔ **`GPIO 19`**
       * Pin 3 (`/WP`) ↔ **`3V3`** (via `10 kΩ`)
       * Pin 4 (`GND`) ↔ **`GND`**
       * Pin 5 (`DI` / MOSI) ↔ **`GPIO 23`**
       * Pin 6 (`CLK`) ↔ **`GPIO 18`**
       * Pin 7 (`/HOLD`) ↔ **`3V3`** (via `10 kΩ`, muss HIGH sein)
       * Pin 8 (`VCC`) ↔ **`3V3`** (niemals `5V`/`VIN`!)
     * **In-Circuit-Risiken bei ESP32:** Über Pin 8 (`VCC`) wird ggf. die gesamte 3,3-V-Schiene der Platine mitgespeist → ALi-SoC kann anlaufen (Bus-Kollision / Überlastung des NodeMCU-3,3-V-Reglers). Deshalb zuerst nur JEDEC-ID (`0x9F`, z. B. `EF 40 17` bei W25Q64) testen, nur Read-Befehl (`0x03`) nutzen, zweimal komplett auslesen und `sha256sum` abgleichen (im Zweifel Chip auslöten).
4. **Ergebnis:** 100 % exakter `8.388.608`-Byte-Dump (`8 MB`) des SPI-Flashs inklusive Bootloader, Chunks, Zertifikate und Werkseinstellungen.

