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

## 3. Analyse der Software-Wege

### Methode 1: Cloud-Download über TiViCon WMS/CDMS API
* **Mechanismus:** Die offizielle TV2Smart-App sendet beim Start eine Update-Anfrage an:
  `POST https://wms.tiviconsolutions.com/api/updater/updates/upd`
  mit API-Key `NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB`.
* **Ergebnis der Live-Prüfung:**
  * Getestet für alle bekannten OEM-Kunden-IDs:
    * `6174` (WISI OR S2D Live-Dongle)
    * `7` (Schwaiger DSRD0100)
    * `24` (WISI Austria)
    * `48` (WISI Spain)
    * `220` (WISI Spain Wision)
  * Über alle Versionsstände (`0`, `1`, `256`) und Hardwaretypen (`0`, `26`, `OR S2D`, `TC711`) antwortet der Server mit:
    `{"status": "NO_UPDATE"}`.
* **Fazit:** Aktuell stellt TiViCon über die Cloud keine öffentlich downloadbare Firmware mehr bereit.

---

### Methode 2: Extraktion aus APKs (Bundled Offline-Firmware)
* **Mechanismus:** Das SDK (`onDongleCommunicationStatusHelpText.java`) prüft den Ordner `assets/dongle-firmware/` auf `.abs`-Dateien, um Offline-Updates zu unterstützen.
* **Ergebnis:**
  * In der aktuellen APK (`TV2Smart_3.M20260803.0`) liegt in `assets/dongle-firmware/` lediglich die Platzhalterdatei `here_put_abs` (0 Byte).
  * Es existiert eine Android-TV-Variante (`com.tivicon.tv2smart.atv`), die laut Bedienungsanleitung für das "USB Upgrade über Speicherstick" ausgelegt ist.
* **Nächster Schritt:** Archivierte / ältere APK-Versionen und die ATV-Builds auf gebündelte `.abs`-Dateien durchsuchen.

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
    * Standard-Modus: USB-CDC / Serial / Bulk-Interface für PC-Kommunikation.
    * Bootloader-/Recovery-Modus (z. B. durch Halten eines internen Tasters oder bei leerem Flash): Meldet sich als ALi USB Bootloader / DFU Device.
    * Tools wie *ALi Universal Upgrade Tool*, *ALi M35xx PC Tool* oder Open-Source-Treiber können über diesen Port Firmware auslesen oder flashen.
* **Status:** Der Dongle ist aktuell per LAN im Netzwerk (`192.168.178.32`). Wenn der Nutzer den Dongle per USB-C an den PC anschließt, kann die USB-Gerätekennung (VID/PID) ausgelesen und die Bootloader-Kommunikation getestet werden.

---

## 4. Hardware-Extraktion (Garantierter Fallback)

Falls kein Download verfügbar ist und kein USB-Lesezugriff besteht, ist das physische Auslesen der Standardweg:

1. **Gehäuse öffnen:** Der Dongle (65 x 65 x 20 mm) ist geklipst.
2. **Flash-Identifikation:** 8-Pin SPI NOR Flash Chip auf der Platine (z. B. Winbond W25Q64JV, 8 MB).
3. **Auslesen mit SOIC-8 Clip:**
   * Ein SOIC-8 Prüfclip (Test-Clip) wird auf den Chip gesetzt (ohne Löten).
   * Programmierer: Günstiger **CH341A USB-Programmer** (oder ESP32 / Raspberry Pi mit `flashrom`).
   * Befehl: `flashrom -p ch341a_spi -r wisi_or_s2d_dump.bin`.
4. **Ergebnis:** 100 % exakter 8 MB Dump des SPI-Flashs inklusive Bootloader, Chunks, Zertifikate und Werkseinstellungen.
