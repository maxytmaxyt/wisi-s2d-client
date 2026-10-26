# WISI OR S2D (TiViCon / Schwaiger DSRD0100) — Technische Gesamtreferenz & Reverse-Engineering-Dokumentation

**Stand:** Oktober 2026  
**Zielsystem:** WISI OR S2D DVB-S2 Netzwerk-/USB-Dongle (OEM TiViCon OR S2D / Schwaiger DSRD0100)  
**Status:** Vollständig analysiert, Python-Client betriebsbereit, SDK dekompiliert, Protokoll auf TCP/UDP- sowie USB-Ebene verifiziert.

---

## 1. System- & Hardware-Architektur

### 1.1 Geräteidentifikation & Abgrenzung
* **Exakte Modellbezeichnung:** WISI OR S2D (DVB-S2 Free-To-Air SAT Dongle).
* **Baugleiche OEM-Varianten:** Schwaiger DSRD0100, TiViCon OR S2D.
* **Wichtige Abgrenzung:** Nicht zu verwechseln mit älteren Geräten wie dem **WISI O2D**, **Tivizen** oder älteren **TiViCon**-Mobil-Tuner-Generationen. Das Protokoll des OR S2D basiert zwar auf der APIX-Befehlsklasse von iCube Technology, unterscheidet sich jedoch signifikant im Transport (TCP-XML-Kanalliste statt UDP-Binary-Blob).

### 1.2 Hardware-Spezifikationen
* **SoC / Prozessor:** 32-Bit RISC-CPU mit 650 MHz Taktfrequenz.
* **Arbeitsspeicher & Flash:** 128 MB DDR-RAM, 8 MB SPI Flash-Speicher.
* **DVB-Frontend:** DVB-S/S2 Tuner & Demodulator (950–2150 MHz) mit Unterstützung für DiSEqC 1.0/1.1/1.2 (Port A–D, Unicable, USALS) sowie LNB-Spannungsumschaltung (13V Vertikal / 18V Horizontal, 22 kHz Tonburst).
* **Netzwerkschnittstelle:** 100 Mbit/s Fast-Ethernet (RJ-45) und Dual-Band Wi-Fi (2,4 GHz / 5 GHz).
* **Physischer Anschluss:** USB-C Buchse (dient zur Stromversorgung, für Firmware-Updates und die direkte USB-OTG-Verbindung mit Android-TV-Boxen oder Smartphones).

### 1.3 Betriebsmodi
1. **Netzwerk-Streaming-Modus (LAN / WLAN):** Der Dongle agiert als autonomer DVB-over-IP-Server im Heimnetzwerk. Er nimmt Befehle über TCP Port 8802 entgegen und liefert MPEG-TS-Videostreams über UDP Port 8800 an Clients.
2. **USB-Host / OTG-Modus:** Bei direkter USB-C-Kopplung mit einer Android-TV-Box oder einem Smartphone (z. B. Sony Xperia 10) schaltet der Dongle seine Netzwerkinterfaces ab. Die Kommunikation erfolgt transparent über USB Bulk-Endpunkte (Bulk OUT `0x01` für Steuerung, Bulk IN `0x81` für Nutzdaten) via `android.hardware.usb`.

---

## 2. Protokoll-Architektur & Transportschicht

### 2.1 Emulation von USB BOT über TCP
Die Firmware emuliert das USB Mass Storage Class Bulk-Only Transport (BOT) Protokoll direkt über ein verbindungsorientiertes TCP-Socket auf Port 8802.

```
+-------------------------------------------------------------------+
| Application Layer: APIX DVB Command Set (0xF6 - 0xFF)             |
+-------------------------------------------------------------------+
| Command Encapsulation: SCSI CDB (16 Bytes inside CBW)             |
+-------------------------------------------------------------------+
| Transport Layer: USB BOT Framing (31-Byte CBW / 13-Byte CSW)      |
+-------------------------------------------------------------------+
| Network Layer: TCP (Port 8802 Control) / UDP (Port 8800 Stream)   |
+-------------------------------------------------------------------+
```

### 2.2 Anatomie des 31-Byte Command Block Wrappers (CBW)
Jedes Steuerkommando wird in einen 31 Byte langen USBC-Rahmen gekapselt:

| Byte-Offset | Feldbezeichnung | Länge | Wert / Hex | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `dCBWSignature` | 4 B | `55 53 42 43` | ASCII `"USBC"` (CBW Magic) |
| `0x04 - 0x07` | `dCBWTag` | 4 B | `A0 CB 03 37` | Transaktions-ID / Magic Tag (konstant) |
| `0x08 - 0x0B` | `dCBWDataTransferLength` | 4 B | `uint32_BE` | Erwartete Datenlänge in der Datenphase |
| `0x0C` | `bmCBWFlags` | 1 B | `0x80` / `0x00` | Direction (`0x80` = Device-to-Host, `0x00` = Host-to-Device) |
| `0x0D` | `bCBWLUN` | 1 B | `0x00` | Logical Unit Number (immer 0) |
| `0x0E` | `bCBWCBLength` | 1 B | `0x10` | CDB-Länge (16 Bytes = `0x10`) |
| `0x0F` | `CDB[0]` Prefix | 1 B | `0xF6` bis `0xFF` | APIX Opcode-Hauptklasse |
| `0x10 - 0x13` | `CDB[1..4]` Magic | 4 B | `41 50 49 58` | ASCII `"APIX"` |
| `0x14` | `CDB[5]` Sub-Opcode | 1 B | `0x01`, `0x16`, `0x20` etc. | Sub-Befehl innerhalb der APIX-Klasse |
| `0x15 - 0x1E` | `CDB[6..15]` Payload | 10 B | `Bytes` | Befehlsspezifische Parameter & Padding (Inline-Payload) |

### 2.3 Anatomie des 13-Byte Command Status Wrappers (CSW)
Jede Antwort des Dongles schließt mit einem 13-Byte-Status-Trailer ab:

| Byte-Offset | Feldbezeichnung | Länge | Wert / Hex | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `dCSWSignature` | 4 B | `55 53 42 53` | ASCII `"USBS"` (CSW Magic) |
| `0x04 - 0x07` | `dCSWTag` | 4 B | `A0 CB 03 37` | Spiegelt den `dCBWTag` der Anfrage |
| `0x08 - 0x0B` | `dCSWDataResidue` | 4 B | `uint32_BE` | Verbleibende Differenz-Bytes |
| `0x0C` | `bCSWStatus` | 1 B | `0x00` | Status (`0x00` = Success, `0x01` = Fail, `0x02` = Phase Error) |

---

## 3. Vollständige Opcode- & Befehlsreferenz (CreNova SDK)

Die Dekompilierung des SDKs (`com.crenova.tv.dongle.dvb.sdk`) liefert die vollständige Matrix aller Opcode-Prefixes und ihrer Sub-Befehle:

| Haupt-Opcode | Sub-Opcode | SDK Command / Funktion | Inline-Payload (Bytes 21+) / Parameter |
| :--- | :--- | :--- | :--- |
| **`0xF6`** | `0x01` | Channel Tune / Activate | `payload[0..1]`: 16-Bit Kanal-Index (Big-Endian) |
| **`0xF6`** | `0x02` | Signal Status Poll | Liefert Lock-Status, RSSI (Stärke %) und SNR (Qualität %) |
| **`0xF6`** | `0x03` | Prepare Channel | `prog_idx` Vorbereitung im Dongle-Demux |
| **`0xF6`** | `0x16` | Handshake Phase 1 | Statusabfrage (`0x00` = Initialisierung, `0x01` = Bereit) |
| **`0xF6`** | `0x17` | Handshake Phase 2 / Confirm | Bestätigung der Tuning-Bereitschaft (`flag = 0x00`) |
| **`0xF6`** | `0x20` | Get `ch_List` Size | Liefert 8 Bytes, Bytes 0–3 = XML-Größe in Bytes (uint32_BE) |
| **`0xF6`** | `0x21` | Get `ch_List` Data | Ruft die komplette Kanalliste im XML-Format ab |
| **`0xF6`** | `0x32` | Get `ch_Info` Size | Liest die XML-Länge für kanalbezogene Zusatzdaten |
| **`0xF6`** | `0x33` | Get `ch_Info` Data | Ruft die `<ch_Info>` XML-Metadaten ab |
| **`0xF7`** | `0x01` | DVB-S/S2 Transponder Set | Frequenz in kHz (Bytes 21–24), Symbolrate in kS/s (Bytes 25–28) |
| **`0xF7`** | `0x02` | Tuner Standard & Modus | Standard (4 = DVB-S2), Modulation (0 = QPSK, 1 = 8PSK) |
| **`0xF8`** | `0x01` | LNB Power / Spannung | Voltage (0 = Aus, 1 = 13V Vertikal, 2 = 18V Horizontal) |
| **`0xF8`** | `0x02` | 22kHz Tonburst | Ton-Signal (0 = Aus / Low-Band, 1 = Ein / High-Band, 2 = Auto) |
| **`0xF8`** | `0x03` | DiSEqC 1.0 Schalter | Port (0 = Direkt, 1 = Port A, 2 = Port B, 3 = Port C, 4 = Port D) |
| **`0xF8`** | `0x04` | DiSEqC 1.1 / Unicable | User-Band Index & Scratchpad-Frequenz |
| **`0xF8`** | `0x07` | TS Stream Enable | Schaltet die MPEG-TS-Ausgabe auf UDP Port 8800 frei |
| **`0xF9`** | `0x01` | DVB Stream Pull / Demux | `byte21 = 0x00` (1. Block) / `0x01` (Folgeblöcke), Video/Audio-PIDs |
| **`0xF9`** | `0x0A` | Speedtest Execution | Ruft `getSpeedTestMbps()` ab (48.128 Byte Testdaten-Payload) |
| **`0xFA`** | `0x00` | Device Discovery Info | Liest Session-Tokens, Netzwerk-Config & MAC-Ableitungen |
| **`0xFA`** | `0x07` | Device Model Name | Liefert String `"OR S2D"` und Seriennummer |
| **`0xFA`** | `0x08` | Network Configuration | Liest IP-Adresse, Subnetzmaske und Gateway (526 Bytes) |
| **`0xFB`** | `0x01` | TS Streaming Control | Globaler Stream-Start (`1`) bzw. Stream-Stop (`0`) |
| **`0xFC`** | `0x01`-`0x05` | Firmware Flash / Update | `0x01` Erase, `0x02` Write, `0x03` Verify (Binary-Blocks ab Byte 31) |
| **`0xFE`** | `0x01` | Get Dongle Info / About | Liest Seriennummer, Chip-ID und Firmware-Version aus |
| **`0xFF`** | `0x00` | System Reset / Reboot | Löst einen Hardware-Neustart des Dongles aus |

---

## 4. Manuelles DVB-S/S2 Tuning & DiSEqC Mechanics

Wenn kein fertiger Eintrag aus der XML-Kanalliste gewählt, sondern ein manueller Frequenz-Scan oder Transponder-Tuning durchgeführt wird, durchläuft das SDK eine 4-stufige Befehlssequenz:

1. **LNB-Konfiguration setzen (`CMD_TUNER_DVBS2_SET_LNB` = 126 / `0x7E`):**
   * Stellt LNB-Spannung (13V Vertikal vs. 18V Horizontal) und den 22kHz-Super-Heterodyn-Schaltton (High-Band / Low-Band) ein.
2. **DiSEqC-Schaltbefehl senden (`CMD_TUNER_DVBS2_SET_DISEQC` = 127 / `0x7F`):**
   * Schaltet DiSEqC-Relais / Umschalter (Port A, B, C, D) oder übermittelt Unicable- / USALS-Rotorparameter.
3. **Satelliteneinstellungen setzen (`CMD_TUNER_DVBS2_SET_SATELLITE` = 132 / `0x84`):**
   * Übergibt Satellitenname, LOF1 (z. B. 9750 MHz) und LOF2 (z. B. 10600 MHz).
4. **Transponder-Tuning ausführen (`CMD_TUNER_DVBS2_SET` = 125 / `0x7D` / Opcode `0xF7/0x01`):**
   * Übergibt die Ziel-Frequenz (in kHz), Symbolrate (in kS/s), Polarisation und FEC.

* **Zusätzliche Suchlauf- & Tuning-Befehle:**
  * `CMD_START_SCAN_DVBS` (710 / `0x2C6`): Startet den automatischen DVB-S/S2-Sendersuchlauf im Dongle-Demux.
  * `CMD_CHANGE_CHANNEL_BY_SID` (807 / `0x327`): Ermöglicht direktes Umschalten anhand der DVB Service-ID.

---

## 5. Firmware-Update & Server-Endpoints

### 5.1 Online-Update-Architektur (Retrofit & RxJava2)
Die SDK-Klasse `CheckUpdate.java` sowie `CrenovaDongleInit.java` implementieren die automatische Firmware-Prüfung über einen HTTP-REST-Endpoint:

* **HTTP-Request:** `POST <Base-URL>/api/updater/updates/upd`
* **JSON-Anfrage-Payload:**
  ```json
  {
    "_key": "<CDMS_API_KEY>",
    "dongle_sw_version": "1.0.24",
    "dongle_hw_type": "OR_S2D",
    "dongle_customer_id": "WISI",
    "updateType": "release"
  }
  ```
* **JSON-Antwort-Struktur (`CheckUpdate` POJO):**
  * `status`: `"UPDATE"` (Firmware verfügbar) oder `"NO_UPDATE"`.
  * `url`: HTTP-Direkt-Download-Link zum Firmware-Binary (`.bin` / `.img`).
  * `filesize`: Exakte Dateigröße in Bytes.
  * `md5sum`: MD5-Prüfsumme zur Integritätsverifizierung.
  * `change_log`: Beschreibung der Änderungen.
  * `dongle_sw_version`: Neue Versionsnummer.

### 5.2 Flash-Pipeline auf dem Dongle
Bei Vorliegen einer neuen Firmware startet das SDK die lokale Flash-Pipeline:
1. **Dienst-Start:** Aufruf von `CMD_UPDATE_DONGLE_START` (Command ID 400) an den lokalen Android-Dienst (`ACTION_MSG_TO_UPDATE_DONGLE_SERVICE`).
2. **Fortschritts-Broadcasts:** Der Update-Dienst durchläuft und meldet folgende Phasen:
   * `UPDATE_DONGLE_STATUS_TRANSFER`: Übertragung der Blöcke an den Dongle (Opcode `0xFC/0x02` oder `0xF7/0x01` mit `"FWUP"`-Header).
   * `UPDATE_DONGLE_STATUS_VERIFY`: Prüfen der MD5-Hashwerte auf dem Dongle.
   * `UPDATE_DONGLE_STATUS_ERASE`: Löschen der alten SPI-Flash-Sektoren.
   * `UPDATE_DONGLE_STATUS_WRITE`: Schreiben der neuen Firmware in den Flash.
   * `UPDATE_DONGLE_STATUS_DONE`: Erfolgreicher Abschluss, gefolgt von `0xFF/0x00` (System Reboot).

---

## 6. Protokollablauf im Normalbetrieb (Streaming)

### 6.1 Kanallisten-Abruf via TCP XML (`0xF6 / 0x20` & `0xF6 / 0x21`)
1. **Größenabfrage (`0xF6 / 0x20`):** Anforderung der XML-Länge. Antwort ist ein 8-Byte-Block (erste 4 Bytes = `uint32_BE` XML-Größe, z. B. 61.348 Bytes).
2. **Datenabruf (`0xF6 / 0x21`):** Anforderung der Nutzdaten mit der ermittelten XML-Länge.
3. **XML-Struktur `<ch_List>`:**
   ```xml
   <ch_List>
     <ch type="TV" pol="H" sym="22000" s_id="28721" ts_id="1051"
         freq="10744" prog_idx="1083375616" lcn="69"
         s_name="tagesschau24" fta="1" />
     ...
   </ch_List>
   ```

### 6.2 Tuning & Stream-Pulling (TCP 8802 & UDP 8800)
1. **Handshake (`0xF6 / 0x16` & `0xF6 / 0x17`):** Bereitschaft prüfen und bestätigen.
2. **Kanal vorbereiten (`0xF6 / 0x03`):** Übergabe von `prog_idx`.
3. **Signal-Polling (`0xF6 / 0x02`):** RSSI & SNR abfragen.
4. **Kanal aktivieren (`0xF6 / 0x01`):** CDB Offset 21 & 22 = 16-Bit Kanalindex als Big-Endian.
5. **Stream freigeben (`0xF8 / 0x07`):** MPEG-TS-Ausgabe auf UDP 8800 starten.
6. **UDP Stream Pulling (`0xF9 / 0x01`):** Kontinuierliche UDP-Pulls auf Port 8800. Der Dongle antwortet mit Datenblöcken à 174 MPEG-TS-Paketen (188 Bytes je Paket, Sync-Byte `0x47`).

---

## 7. Reverse Engineering der TV2Smart Android App (`com.tivicon.tv2smart.mobile`)

### 7.1 Security & Native Bibliotheken
* **ADB-Debugging-Sperre:** Das SDK prüft `Settings.Global["adb_enabled"]`. Ist der Wert `1`, verweigert die App den Start (`MSG_COMMUNICATION_FAILED_ADB_DEBUG`). Mit Root (`settings put global adb_enabled 0` oder Xposed) lässt sich dies umgehen.
* `libsecure_module.so`: Beinhaltet CI+-artiges Content-Control für Pay-TV.
* **Hardcodierter Seed in `libsecure_module.so`:**
  * Base64: `THVrZVJhbkRvbHBoQ0krMQ==` \(\rightarrow\) **`LukeRanDolphCI+1`**
  * Key dient nur für verschlüsselte Pay-TV-Kanäle (`0x48xxxxxx`). FTA-Sender benötigen keinen Key.

---

## 8. Python-Client Implementation (`wisi-client`)

Im Verzeichnis `src/` befindet sich der funktionsfähige Python-Client:

* **Kanalliste abrufen:**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --channels
  ```
* **MPEG-TS Stream in Datei aufzeichnen (z. B. Kanal-Index 4 = RTL / ZDF):**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output stream.ts
  ```
* **Stream an VLC weiterleiten:**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --output - | vlc -
  ```

---

## 9. Widerlegte Mythen & Fakten-Check

| Frühere Annahme / Mythos | Widerlegte/Korrigierte Realität |
| :--- | :--- |
| **USBC-Anfragen sind 66 Byte lang** | **Falsch:** Anfragen sind exakt **31 Byte** lang (Standard USB CBW). |
| **USBS-Trailer sind 46 Byte lang** | **Falsch:** Antworten enden mit **13 Byte** USBS-Trailer. |
| **Kanalliste kommt per UDP-Blob (`0xF9/0x0A`)** | **Falsch:** `0xF9/0x0A` ist ein **Speedtest** (`getSpeedTestMbps()`). Kanalliste kommt per **TCP XML** (`0xF6/0x20` + `0xF6/0x21`). |
| **MD5-Challenge/Response für FTA nötig** | **Falsch:** FTA-Streams benötigen **keine Authentifizierung**. |
