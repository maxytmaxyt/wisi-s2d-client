# WISI OR S2D (TiViCon / Schwaiger DSRD0100) — Technische Gesamtreferenz & Reverse-Engineering-Dokumentation

**Stand:** Oktober 2026  
**Zielsystem:** WISI OR S2D DVB-S2 Netzwerk-/USB-Dongle (OEM TiViCon OR S2D / Schwaiger DSRD0100)  
**Status:** Vollständig analysiert, Python-Client betriebsbereit, Protokoll auf TCP/UDP-Ebene verifiziert.

---

## 1. System- & Hardware-Architektur

### 1.1 Geräteidentifikation & Abgrenzung
* **Exakte Modellbezeichnung:** WISI OR S2D (DVB-S2 Free-To-Air SAT Dongle).
* **Baugleiche OEM-Varianten:** Schwaiger DSRD0100, TiViCon OR S2D.
* **Wichtige Abgrenzung:** Nicht zu verwechseln mit älteren Geräten wie dem **WISI O2D**, **Tivizen** oder älteren **TiViCon**-Mobil-Tuner-Generationen. Das Protokoll des OR S2D basiert zwar auf der APIX-Befehlsklasse von iCube Technology, unterscheidet sich jedoch signifikant im Transport (TCP-XML-Kanalliste statt UDP-Binary-Blob).

### 1.2 Hardware-Spezifikationen
* **SoC / Prozessor:** 32-Bit RISC-CPU mit 650 MHz Taktfrequenz.
* **Arbeitsspeicher & Flash:** 128 MB DDR-RAM, 8 MB SPI Flash-Speicher.
* **DVB-Frontend:** DVB-S/S2 Tuner & Demodulator (950–2150 MHz) mit Unterstützung für DiSEqC 1.0/1.2 sowie LNB-Spannungsumschaltung (13V Vertikal / 18V Horizontal, 22 kHz Tonburst).
* **Netzwerkschnittstelle:** 100 Mbit/s Fast-Ethernet (RJ-45) und Dual-Band Wi-Fi (2,4 GHz / 5 GHz).
* **Physischer Anschluss:** USB-C Buchse (dient zur Stromversorgung, für Firmware-Updates und die direkte USB-OTG-Verbindung mit Android-TV-Boxen).

### 1.3 Betriebsmodi
1. **Netzwerk-Streaming-Modus (LAN / WLAN):** Der Dongle agiert als autonomer DVB-over-IP-Server im Heimnetzwerk. Er nimmt Befehle über TCP Port 8802 entgegen und liefert MPEG-TS-Videostreams über UDP Port 8800 an Clients.
2. **USB-Host / OTG-Modus:** Bei direkter USB-C-Kopplung mit einer Android-TV-Box schaltet der Dongle seine Netzwerkinterfaces ab. Die Kommunikation erfolgt transparent über USB Bulk-Endpunkte (Bulk OUT `0x01` für Steuerung, Bulk IN `0x81` für Nutzdaten).

---

## 2. Protokoll-Architektur & Transportschicht

### 2.1 Emulation von USB BOT über TCP
Die Firmware emuliert das USB Mass Storage Class Bulk-Only Transport (BOT) Protokoll direkt über ein verbindungsorientiertes TCP-Socket auf Port 8802.

```
+-------------------------------------------------------------------+
| Application Layer: APIX DVB Command Set (0xF6, 0xF7, 0xF8, 0xF9) |
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
| `0x0F` | `CDB[0]` Prefix | 1 B | `0xF6` / `0xF7` / `0xF8` / `0xF9` | APIX Opcode-Klasse |
| `0x10 - 0x13` | `CDB[1..4]` Magic | 4 B | `41 50 49 58` | ASCII `"APIX"` |
| `0x14` | `CDB[5]` Sub-Opcode | 1 B | `0x01`, `0x16`, `0x20` etc. | Einzelner Befehl innerhalb der APIX-Klasse |
| `0x15 - 0x1E` | `CDB[6..15]` Payload | 10 B | `Bytes` | Befehlsspezifische Parameter & Padding |

### 2.3 Anatomie des 13-Byte Command Status Wrappers (CSW)
Jede Antwort des Dongles schließt mit einem 13-Byte-Status-Trailer ab:

| Byte-Offset | Feldbezeichnung | Länge | Wert / Hex | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `dCSWSignature` | 4 B | `55 53 42 53` | ASCII `"USBS"` (CSW Magic) |
| `0x04 - 0x07` | `dCSWTag` | 4 B | `A0 CB 03 37` | Spiegelt den `dCBWTag` der Anfrage |
| `0x08 - 0x0B` | `dCSWDataResidue` | 4 B | `uint32_BE` | Verbleibende Differenz-Bytes |
| `0x0C` | `bCSWStatus` | 1 B | `0x00` | Status (`0x00` = Success, `0x01` = Fail, `0x02` = Phase Error) |

---

## 3. Befehlsreferenz & Protokollablauf

### 3.1 Initialisierung & Handshake (TCP 8802)
* **Statusabfrage / Handshake Phase 1 (`0xF6 / 0x16`):**
  * Request: CBW mit Opcode `0xF6 / 0x16`, `data_len = 12`.
  * Response: 12 Bytes Daten. Byte `[0]` zeigt den Status: `0x00` = Warten/Initialisierung, `0x01` = Dongle bereit. Enthält auch Geräte-ID (z. B. `04 ff 04 a5 2d`).
* **Bereitschaftsbestätigung Phase 2 (`0xF6 / 0x17`):**
  * Request: CBW mit Opcode `0xF6 / 0x17`, `data_len = 4`.
  * Response: `flag = 0x00` (Bestätigung der Tuning-Bereitschaft).

### 3.2 Kanallisten-Abruf via TCP XML (`0xF6 / 0x20` & `0xF6 / 0x21`)
Im Gegensatz zu älteren Geräten wird die Kanalliste im OR S2D vollständig im XML-Format über TCP abgerufen:
1. **Größenabfrage (`0xF6 / 0x20`):** Anforderung der XML-Länge. Antwort ist ein 8-Byte-Block, wovon die ersten 4 Bytes als `uint32_BE` die exakte XML-Größe in Bytes angeben (im analysierten Datensatz: **61.348 Bytes**).
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
   * `s_id`: DVB Service ID (z.B. `28721`)
   * `prog_idx`: Interner 32-Bit-Bezeichner (FTA-Sender nutzen `0x40xxxxxx`, Pay-TV/verschlüsselte Sender `0x48xxxxxx`).
   * `fta`: `1` = Free-To-Air, `0` = Verschlüsselt.
   * `lcn`: Logical Channel Number (entspricht der Reihenfolge im Flash).

### 3.3 Channel Tuning Mechanics (`0xF6 / 0x01`)
Der Tuning-Ablauf erfordert eine strikte Sequenz über TCP Port 8802:
1. **Kanal vorbereiten (`0xF6 / 0x03`):** Übergabe von `prog_idx`.
2. **Channel Info abrufen (`0xF6 / 0x32` + `0xF6 / 0x33`):** Liefert Zusatz-XML `<ch_Info>` mit Transponderparametern.
3. **Signal-Polling (`0xF6 / 0x02`):** Abfrage von Stärke und Qualität (Byte `[1]` = Stärke %, Byte `[2]` = Qualität %).
4. **Kanal aktivieren (`0xF6 / 0x01`):**
   * CDB Payload Offset 21 & 22 (`payload[0..1]`): Der **interne 16-Bit-Kanalindex** des Dongles als Big-Endian-Integer (z.B. `0x00 0x04` für Kanal-Index 4 = ZDF).
5. **Stream freigeben (`0xF8 / 0x07`):** Öffnet die Stream-Ausgabe auf UDP Port 8800.

### 3.4 UDP Stream Pulling & MPEG-TS Format (UDP 8800)
* **Stream-Init (`0xF9 / 0x02`):** Einmaliges UDP-Paket an Port 8800 zur Initialisierung des Sockets.
* **DVB Pull-Befehl (`0xF9 / 0x01`):**
  * Client fordert jeden Videoblock aktiv per UDP-Request an.
  * Request-Header: `data_len = 0xBC00` (48.128 Bytes), Byte 21 schaltet zwischen `0x00` (erster Block) und `0x01` (folgende Blöcke) um.
* **MPEG-TS Nutzdaten:**
  * Der Dongle antwortet mit Datenblöcken über UDP.
  * Der Client sucht das DVB-Sync-Byte `0x47` und richtet den Videostream an strikten 188-Byte-MPEG-TS-Paketgrenzen aus (typisch 174 TS-Pakete = 32.712 Bytes Nutzdaten pro Block).

### 3.5 Speedtest-Kommando (`0xF9 / 0x0A`)
Die APK-Analyse belegt eindeutig, dass der Befehl `0xF9 / 0x0A` **keine Senderliste** ist, sondern von der App-Methode `getSpeedTestMbps()` für Durchsatzmessungen aufgerufen wird. Ein Request fordert 48.128 Bytes Testdaten an; die Antwort hat eine Gesamtgröße von 48.143 Bytes (48.130 Datenbytes + 13 Bytes USBS-Trailer).

### 3.6 Firmware-Update-Protokoll (`0xF7 / 0x01` & `0xF7 / 0x02`)
Über TCP Port 8802 unterstützt die Firmware das Aufspielen von Binär-Updates:
* **Firmware-Block-Upload (`0xF7 / 0x01`):**
  * Paket beginnt mit der Magischen Signatur `0x46575550` (`"FWUP"` in ASCII).
  * Überträgt die Binar-Image-Blöcke in definierten Chunks.
* **Flash- & Reboot-Kommando (`0xF7 / 0x02`):**
  * Veranlasst den SPI-Flash-Schreibvorgang und den anschließenden Systemneustart des Dongles.

---

## 4. Reverse Engineering der TV2Smart Android App (`com.tivicon.tv2smart.mobile`)

### 4.1 Native Bibliotheken (ARM64 JNI)
* `libsecure_module.so` (229 KB): Beinhaltet ein CI+-artiges Content-Control-System (SAC/CC, Diffie-Hellman Key Exchange) für Pay-TV.
* **Hardcodierter Seed in `libsecure_module.so`:**
  * In der `.rodata`-Sektion findet sich der Base64-String: `THVrZVJhbkRvbHBoQ0krMQ==`
  * Dekodiert: **`LukeRanDolphCI+1`**
  * **Wichtige Erkenntnis:** Dies ist ein Root-Key/Seed für verschlüsselte Pay-TV-Kanäle (`0x48xxxxxx`-prog_idx). **Für normales Free-To-Air (FTA) Streaming ist dieser Key NICHT erforderlich.**
* `libpimbridge.so` & `libpimdec.so`: PIM-Decoder für proprietäres Multicast-CA.
* `libvlc.so`: VLC-Player-Core für die Videowiedergabe.

### 4.2 App-Datenbank & ExoPlayer-Integration
* Die App verwaltet lokal eine SQLite-Datenbank `dongleChListDB.db` mit Schemata für Sender, EPG, Bouquets und Favoriten.
* Zur Übergabe des empfangenen MPEG-TS-Streams an den ExoPlayer nutzt die App eine `ParcelFileDescriptor.createPipe()` FIFO-Pipe.

---

## 5. Python-Client Implementation (`wisi-client`)

Im Verzeichnis `src/` befindet sich ein vollständig funktionstüchtiger Python-3.10+ Client:

### 5.1 Verzeichnisstruktur
```
src/
├── wisi.py            # CLI-Haupt-Einstiegspunkt
├── protocol.py        # USBC/CSW CBW-Builder, Sockets & Konstanten
├── channels.py        # XML-Fetcher & Parser für 0xF6/0x20 + 0xF6/0x21
├── stream.py          # Tuning-Ablauf & UDP MPEG-TS Stream Receiver
├── keepalive.py       # Hintergrund-Thread für 0xF6/0x16 Heartbeat
├── models.py          # Datenstrukturen (Channel, ServiceEntry)
├── wisi_pcap.py       # PCAP-Analyse-Tool für Mitschnitte
└── wisi_probe.py      # Opcode-Tester für unentdeckte APIX-Befehle
```

### 5.2 Verifizierte CLI-Befehle
* **Kanalliste abrufen:**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --channels
  ```
* **MPEG-TS Stream in Datei aufzeichnen (z.B. Kanal-Index 4 = RTL / ZDF):**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output stream.ts
  ```
* **Stream direkt an VLC-Player weiterleiten:**
  ```bash
  python src/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --output - | vlc -
  ```
* **PCAP-Mitschnitt analysieren:**
  ```bash
  python src/wisi.py --pcap "research/PCAPdroid_12_Okt._16_16_04.pcap"
  ```

---

## 6. PCAP-Traffic-Analyse & Widerlegte Mythen

### 6.1 Zusammenfassung der analysierten Mitschnitte
* `capture_pcapdroid_2026-10-11.pcap` (3.284 Pakete): Zeigt EPG-Abfragen (`0xF6/0x30` / `0x31`) und UDP-Antworten.
* `PCAPdroid_12_Okt._16_16_04.pcap` (940 Pakete): Belegt das Laden der Kanalliste über TCP XML (`0xF6/0x20` + `0xF6/0x21`).
* `PCAPdroid_12_Okt._16_28_17.pcap` (1.197 Pakete): Belegt den vollständigen Tune- & Stream-Ablauf (`0xF6/0x03` → `0xF6/0x01` → `0xF8/0x07` → `0xF9/0x01`).

### 6.2 Widerlegte Annahmen & Klarstellungen
| Frühere Annahme / Mythos | Widerlegte/Korrigierte Realität |
| :--- | :--- |
| **USBC-Anfragen sind 66 Byte lang** | **Falsch:** Anfragen sind exakt **31 Byte** lang (Standard USB CBW). 35-Byte-Auth-Erweiterungen existieren im normalen Betrieb nicht. |
| **USBS-Trailer sind 46 Byte lang** | **Falsch:** Antworten enden mit **13 Byte** USBS-Trailer. |
| **Kanalliste kommt per UDP-Blob (`0xF9/0x0A`)** | **Falsch:** `0xF9/0x0A` ist ein **Speedtest**. Die Kanalliste wird sauber per **TCP XML** (`0xF6/0x20` + `0xF6/0x21`) übertragen. |
| **MD5-Challenge/Response für FTA nötig** | **Falsch:** FTA-Streams benötigen **keine Authentifizierung**. Der hardcodierte Key `LukeRanDolphCI+1` dient nur Pay-TV (CI+). |

---

## 7. Offene Punkte & Zukünftige Meilensteine
1. **Live-Kanalwechsel mit variierenden Indizes:** Verifizierung weiterer 16-Bit-Kanalindizes bei laufendem UDP-Stream.
2. **Scan-PCAP aufzeichnen:** Erfassung eines Sendersuchlaufs zur Analyse der dynamischen Zuweisung interner Kanalindizes im Flash-Speicher.
3. **Erkundung unbekannter Opcodes:** systematische Prüfung ungenutzter APIX-Sub-Opcodes im Bereich `0x04` bis `0x1F` mit `wisi_probe.py`.
