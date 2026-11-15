# WISI OR S2D (TiViCon / Schwaiger DSRD0100) — Technische Gesamtreferenz & Reverse-Engineering-Dokumentation

**Stand:** November 2026  
**Zielsystem:** WISI OR S2D DVB-S2 Netzwerk-/USB-Dongle (OEM TiViCon OR S2D / Schwaiger DSRD0100)  
**Status:** Vollständig analysiert, Python-Client live gegen Hardware verifiziert (`--channels`, `--epg`, `--stream`, `--decrypt`), SDK dekompiliert, Protokoll auf TCP/UDP- sowie USB-Ebene bestätigt.

---

## 1. System- & Hardware-Architektur

### 1.1 Geräteidentifikation & Abgrenzung
* **Exakte Modellbezeichnung:** WISI OR S2D (DVB-S2 SAT Dongle).
* **Baugleiche OEM-Varianten:** Schwaiger DSRD0100, TiViCon OR S2D.
* **Wichtige Abgrenzung:** Nicht zu verwechseln mit älteren Geräten wie dem **WISI O2D**, **Tivizen** oder älteren **TiViCon**-Mobil-Tuner-Generationen. Das Protokoll des OR S2D basiert auf der APIX-Befehlsklasse von iCube / CreNova, überträgt die Kanalliste und EPG-Daten jedoch als XML über TCP Port 8802.

### 1.2 Hardware-Spezifikationen
* **SoC / Prozessor:** 32-Bit RISC-CPU mit 650 MHz Taktfrequenz.
* **Arbeitsspeicher & Flash:** 128 MB DDR-RAM, 8 MB SPI Flash-Speicher.
* **DVB-Frontend:** DVB-S/S2 Tuner & Demodulator (950–2150 MHz) mit Unterstützung für DiSEqC 1.0/1.1/1.2 (Port A–D, Unicable, USALS) sowie LNB-Spannungsumschaltung (13V Vertikal / 18V Horizontal, 22 kHz Tonburst).
* **Netzwerkschnittstelle:** 100 Mbit/s Fast-Ethernet (RJ-45) und Dual-Band Wi-Fi (2,4 GHz / 5 GHz).
* **Physischer Anschluss:** USB-C Buchse (Stromversorgung, Firmware-Updates und direkte USB-OTG-Verbindung mit Android-TV-Boxen oder Smartphones).

---

## 2. Protokoll-Architektur & Transportschicht

### 2.1 Emulation von USB BOT über TCP/UDP
Die Firmware emuliert das USB Mass Storage Class Bulk-Only Transport (BOT) Protokoll direkt über TCP Port 8802 (Steuerung/Metadaten) und UDP Port 8800 (MPEG-TS-Streaming):

```text
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
| `0x0F` (`15`) | `CDB[0]` Prefix | 1 B | `0xF6` bis `0xFF` | APIX Opcode-Hauptklasse |
| `0x10 - 0x13` | `CDB[1..4]` Magic | 4 B | `41 50 49 58` | ASCII `"APIX"` |
| `0x14` (`20`) | `CDB[5]` Sub-Opcode | 1 B | `0x02`, `0x03`, `0x16` etc. | Sub-Befehl innerhalb der APIX-Klasse |
| `0x15 - 0x1E` | `CDB[6..15]` Payload | 10 B | `Bytes` (`21..30`) | Befehlsspezifische Parameter & Padding (Inline-Payload) |

### 2.3 Datenphase & 13-Byte Command Status Wrapper (CSW)
* **2-Byte Antwort-Echo:** Jede TCP-Datenphase vom Dongle beginnt mit den 2 Bytes `[opcode, subopcode]` (z. B. `f6 16 ...`, `f6 03 ...`, `f6 31 <?xml ...`), bevor die eigentlichen Nutzdaten folgen.
* **13-Byte USBS-Trailer:** Jede Antwort schließt mit `55 53 42 53 A0 CB 03 37 <4B residue> <1B status>` (`"USBS..."`) ab.

---

## 3. Verifizierte Opcode- & Befehlsreferenz (CreNova SDK & PCAPs)

| Haupt-Opcode | Sub-Opcode | SDK Command / Funktion | Verifizierter Inline-Payload (USBC Bytes 21–30) & Antwort |
| :--- | :--- | :--- | :--- |
| **`0xF6`** | `0x01` | Hardware Tuner Set / Reset | `flags=0x00`, `data_len=45` (+45 B Transponderdaten). Mit `0` = Tuner-Reset beim Beenden |
| **`0xF6`** | `0x02` | Signal Status Poll | `data_len=17`; Antwort `f6 02 <lock> <strength_%> <quality_%> ...` |
| **`0xF6`** | `0x03` | Tune Channel by `prog_idx` | `data_len=4`; Bytes `21..24` = `00 00 00 02`, Bytes `25..28` = `prog_idx` (`uint32_BE`). Antwort: `f6 03 <lock> <fta>` |
| **`0xF6`** | `0x16` | Handshake / Keep-Alive | `data_len=12`; Antwort `f6 16 <status> <5B dev_id> 00 00 00 00` (`r[2] == 0x01` = bereit) |
| **`0xF6`** | `0x17` | Session Init / Disconnect | `data_len=4`; `byte21=0x00` (Init beim Start) bzw. `byte21=0x01` (Session-Disconnect beim Beenden) |
| **`0xF6`** | `0x20` | Get `ch_List` Size | `data_len=8`; Antwort `f6 20 <uint32_BE size> 00 00` |
| **`0xF6`** | `0x21` | Get `ch_List` Data | `data_len=size`; Antwort `f6 21 <?xml ...><ch_List>...</ch_List>\x00\x00` |
| **`0xF6`** | `0x22` | `ch_List` Ack | `data_len=8`, Bytes `21..24` = `size`; Antwort `f6 22 ...` (8 Bytes) |
| **`0xF6`** | `0x30` | Get `epg_Data` Size | `data_len=6`, Bytes `25..28` = `prog_idx`; Antwort `f6 30 <uint32_BE size>` |
| **`0xF6`** | `0x31` | Get `epg_Data` XML | `data_len=size`, Bytes `25..28` = `prog_idx`; Antwort `f6 31 <?xml ...><epg_Data>...</epg_Data>\x00\x00` |
| **`0xF6`** | `0x32` | Get `ch_Info` Size | `data_len=6`, Bytes `25..28` = `prog_idx`; Antwort `f6 32 <uint32_BE size>` |
| **`0xF6`** | `0x33` | Get `ch_Info` XML | `data_len=size`, Bytes `25..28` = `prog_idx`; Antwort `f6 33 <?xml ...><ch_Info>...</ch_Info>\x00\x00` |
| **`0xF6`** | `0x35` | Get `event_desc` Size | `data_len=6`, Bytes `23..24` = `event_id`, Bytes `25..28` = `prog_idx` |
| **`0xF6`** | `0x36` | Get `event_desc` XML | `data_len=size`, Bytes `23..24` = `event_id`, Bytes `25..28` = `prog_idx` |
| **`0xF8`** | `0x07` | Stream / Recording Stop | **35 Bytes** (`flags=0x00`, `data_len=4`, 31B USBC + `01 00 00 00`). Stoppt den Stream beim Beenden! |
| **`0xF9`** | `0x02` | UDP Stream Socket Init | `data_len=0`, `flags=0x00`, `byte21=0x01`; Antwort: 13 B `USBS` auf UDP 8800 |
| **`0xF9`** | `0x01` | UDP DVB Stream Pull | `data_len=0xBC00` (`48.128`), `flags=0x80`; `byte21=0x00` (Start / nach Erfolg), `byte21=0x01` (Retry nach Timeout). Antwort: `48.205 B` (`48.128B TS + 64B EXTRACSW + 13B USBS`) |
| **`0xF9`** | `0x0A` | Speedtest Execution | `getSpeedTestMbps()`, `data_len=0xBC00` (keine Kanal-Datenbank!) |

---

## 4. Link-Verschlüsselung der MPEG-TS-Pakete (AES-128-ECB)

Ein zentrales Ergebnis der Live-Verifikation und APK-Dekompilierung (`com.crenova.tv.dongle.dvb.sdk.ui.player.a.onDongleCommunicationStatusHelpText`):

* **Auch bei freien Sendern (`FTA`, `prog_idx = 0x40xxxxxx`)** verschlüsselt der Dongle alle Video-, Audio- und Teletext-TS-Pakete vor dem UDP-Versand und setzt im 4-Byte-TS-Header `transport_scrambling_control = 2` (`(pkt[3] >> 6) & 3 == 2`).
* Lediglich PSI-Tabellen wie PAT (`PID 0x0000`) und PMT bleiben unverschlüsselt (`transport_scrambling_control = 0`).
* **Entschlüsselung (`src/decrypt.py`):**
  * Chiffre: **`AES-128-ECB` (`AES/ECB/NoPadding`)**
  * Statischer 16-Byte-Schlüssel: **`1234567880ABCDEF1234567880ABCDEF`**
  * Für jedes 188-Byte-Paket mit `pkt[0] == 0x47`, `(pkt[3] >> 6) & 3 == 2` und `((pkt[3] >> 4) & 1) == 1`:
    1. `pkt[3] &= 0x7F` (löscht das Scrambling-Bit).
    2. Adaptation-Field (falls `(pkt[3] & 0x30) == 0x30`, Länge `adapt_len = pkt[4] + 1`) wird unverändert übersprungen.
    3. Vom Payload (`pay_len = 184 - adapt_len` ab Offset `4 + adapt_len`) werden `enc_len = (pay_len // 16) * 16` Bytes per `AES-128-ECB` entschlüsselt; die restlichen `< 16` Bytes am Paketende sind unverschlüsselt.

---

## 5. Pay-TV & Native Bibliotheken (`0x48xxxxxx`)

* **ADB-Debugging-Sperre:** Das SDK prüft `Settings.Global["adb_enabled"]`. Ist der Wert `1`, verweigert die App den Start (`MSG_COMMUNICATION_FAILED_ADB_DEBUG`).
* **`libsecure_module.so`:** Beinhaltet CI+-artiges Content-Control (SAC/CC-Protokoll, Diffie-Hellman) für Pay-TV-Sender (`prog_idx` mit Präfix `0x48xxxxxx`).
* **Hardcodierter Seed in `libsecure_module.so`:** Base64 `THVrZVJhbkRvbHBoQ0krMQ==` → **`LukeRanDolphCI+1`**.

---

## 6. Python-Client (`src/`)

* **Kanalliste abrufen:**
  ```bash
  python src/wisi/wisi.py --ip 192.168.178.32 --channels
  ```
* **MPEG-TS-Stream aufnehmen und am Ende automatisch entschlüsseln:**
  ```bash
  python src/wisi/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output stream.ts --decrypt
  ```
* **Gespeicherte `.ts`-Datei nachträglich entschlüsseln:**
  ```bash
  python src/wisi/decrypt.py stream.ts
  # oder:
  python src/wisi/wisi.py --decrypt-ts stream.ts
  ```
* **EPG abrufen:**
  ```bash
  python src/wisi/wisi.py --ip 192.168.178.32 --epg --epg-limit 10 --epg-output epg.json
  ```

---

## 7. Widerlegte Mythen & Fakten-Check

| Frühere Annahme / Mythos | Verifizierte Realität |
| :--- | :--- |
| **`connect()` prüft `r[0] == 0x01`** | **Falsch:** Jede TCP-Antwort beginnt mit 2 Echo-Bytes (`f6 16`); der Status steht in **`r[2]`**. |
| **`0xF6/0x03` hat `prog_idx` an Bytes 21–24** | **Falsch:** Bytes 21–24 sind der Modus `00 00 00 02`, `prog_idx` steht an **Bytes 25–28**. |
| **`0xF8/0x07` schaltet den Stream beim Start frei** | **Falsch:** `0xF8/0x07` (35 Bytes inkl. `01 00 00 00`) ist der **Stream-Stop-Befehl** beim Beenden. |
| **`0xF9/0x01` nutzt `byte21=0x01` für alle Folgeblöcke** | **Falsch:** `byte21=0x00` fordert den nächsten Block nach Erfolg an; `byte21=0x01` ist **nur Retry nach Timeout**. |
| **FTA-Streams sind auf UDP unverschlüsselt** | **Falsch:** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`tsc=2`) mit **AES-128-ECB** (`1234567880ABCDEF1234567880ABCDEF`). |
| **Kanalliste kommt per UDP-Blob (`0xF9/0x0A`)** | **Falsch:** `0xF9/0x0A` ist ein **Speedtest** (`getSpeedTestMbps()`). Kanalliste kommt per **TCP XML** (`0xF6/0x20` + `0xF6/0x21`). |
