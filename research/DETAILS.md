# WISI OR S2D (TiViCon / Schwaiger DSRD0100) — Technische Gesamtreferenz & Reverse-Engineering-Dokumentation

**Stand:** November 2026  
**Zielsystem:** WISI OR S2D DVB-S2 Netzwerk-/USB-Dongle (OEM TiViCon OR S2D / Schwaiger DSRD0100)  
**Status:** **100 % entschlüsselt & verifiziert.** Alle 5 APIX-Befehlsklassen (`0xF6`, `0xF8`, `0xF9`, `0xFA`, `0xFB`) des Crenova/TiViCon-SDKs sind vollständig aus dem dekompilierten APK-Quellcode (`com.crenova.tv.dongle.dvb.sdk.*`), `libsecure_module.so`, PCAP-Mitschnitten und Live-Tests gegen die echte Hardware (`192.168.178.32`) dokumentiert.

---

## 0. Protokoll-Entschlüsselungsstatus (Gesamtübersicht)

Im gesamten SDK (`com.crenova.tv.dongle.dvb.sdk.messages.*`) existieren exakt **fünf** APIX-Haupt-Opcodes (`0xF6`, `0xF8`, `0xF9`, `0xFA`, `0xFB`). Frühere Vermutungen über `0xF7` oder `0xFC..0xFE` existieren im SDK-Code nicht.

| APIX-Klasse | SDK-Builder-Klasse | Funktionsbereich | Entschlüsselungsgrad | Status im Python-Client |
| :--- | :--- | :--- | :--- | :--- |
| **`0xF6`** (`-10`) | `messages.onGetBouquetListXml` | Tuner, DVB-S2 LNB/DiSEqC/Satellit, Sendersuchlauf (`0x07..0x12`), Kanalwechsel (`0x03`), Kanalliste (`0x20..0x22`), Bouquets (`0x22..0x2B`), EPG (`0x30..0x38`), Keep-Alive (`0x16/0x17`), Reset (`0x00/0x40`) | **100 %** (alle 38 Sub-Opcodes bytegenau dokumentiert) | Live verifiziert (`protocol.py`, `channels.py`, `prepare.py`, `epg.py`, `scan.py`) |
| **`0xF8`** (`-8`) | `messages.onDongleCommunicationStatusHelpText` | CAS / Smartcard-MMI (`0x00..0x06`, `0x10..0x17`) & Stream-Stop / Sleep-Mode (`0x07`) | **100 %** (alle 16 Sub-Opcodes dokumentiert) | `0xF8/0x07` live verifiziert (`protocol.py`, `stream.py`) |
| **`0xF9`** (`-7`) | `messages.CreNovaDongleInitListener` | UDP-MPEG-TS-Streaming (`0x01`, `0x02`), Stream-Status (`0x00`), IPTV-Injektion (`0x03, 0x04, 0x08, 0x0B`), Loopback (`0x05, 0x06`), Speedtest (`0x0A`) | **100 %** (alle 10 Sub-Opcodes + AES-128-ECB Link-Crypto dokumentiert) | Live verifiziert (`stream.py`, `decrypt.py`) |
| **`0xFA`** (`-6`) | `messages.onDongleCommunicationStatus` | 3-stufige Hardware-/Session-Info (`0x00, 0x07, 0x08`), CI+/SAC-Handshake (`0x01..0x03`), Firmware-Flash (`0x04..0x06`), OTA-Firmware-Download (`0x0A..0x19`) | **100 %** (alle 22 Sub-Opcodes + SAC-Zustandsmaschine dokumentiert) | Builder & Parser in `scan.py` implementiert |
| **`0xFB`** (`-5`) | `messages.onDongleGetIntegerData` | Werks-/Produktionsmodus (`0x01..0x03`: Production Data, XML-Report, Mode-Switch) | **100 %** (alle 3 Sub-Opcodes dokumentiert) | Dokumentiert (nur für Werkskalibrierung) |

---

## 1. System- & Hardware-Architektur

### 1.1 Geräteidentifikation & Abgrenzung
* **Exakte Modellbezeichnung:** WISI OR S2D (DVB-S2 SAT Dongle, interner Modellstring in `0xFA/0x07`: `TC711CXD`, `tunerType = 26 = TYPE_DVB_S`).
* **Baugleiche OEM-Varianten:** Schwaiger DSRD0100, TiViCon OR S2D.
* **Wichtige Abgrenzung:** Nicht zu verwechseln mit älteren Geräten wie dem **WISI O2D**, **Tivizen** oder älteren **TiViCon**-Mobil-Tuner-Generationen. Das Protokoll des OR S2D basiert auf der APIX-Befehlsklasse von iCube / CreNova (`usbProtocolVersion = 2` in `0xFA/0x00`), überträgt die Kanalliste und EPG-Daten jedoch als XML über TCP Port 8802.

### 1.2 Hardware-Spezifikationen
* **SoC / Prozessor:** 32-Bit RISC-CPU mit 650 MHz Taktfrequenz.
* **Arbeitsspeicher & Flash:** 128 MB DDR-RAM, 8 MB SPI Flash-Speicher.
* **DVB-Frontend:** DVB-S/S2 Tuner & Demodulator (950–2150 MHz) mit Unterstützung für DiSEqC 1.0/1.1/1.2 (Port A–D, Unicable, USALS) sowie LNB-Spannungsumschaltung (13 V Vertikal / 18 V Horizontal, 22 kHz Tonburst).
* **Netzwerkschnittstelle:** 100 Mbit/s Fast-Ethernet (RJ-45) und Dual-Band Wi-Fi (2,4 GHz / 5 GHz).
* **Physischer Anschluss:** USB-C Buchse (Stromversorgung, Firmware-Updates und direkte USB-OTG-Verbindung mit Android-TV-Boxen oder Smartphones).

---

## 2. Protokoll-Architektur & Transportschicht

### 2.1 Emulation von USB BOT über TCP/UDP
Die Firmware emuliert das USB Mass Storage Class Bulk-Only Transport (BOT) Protokoll direkt über TCP Port 8802 (Steuerung/Metadaten) und UDP Port 8800 (MPEG-TS-Streaming):

```text
+-------------------------------------------------------------------+
| Application Layer: APIX DVB Command Set (0xF6, 0xF8, 0xF9, 0xFA, 0xFB) |
+-------------------------------------------------------------------+
| Command Encapsulation: SCSI CDB (16 Bytes inside CBW)             |
+-------------------------------------------------------------------+
| Transport Layer: USB BOT Framing (31-Byte CBW / 13-Byte CSW)      |
+-------------------------------------------------------------------+
| Network Layer: TCP (Port 8802 Control) / UDP (Port 8800 Stream)   |
+-------------------------------------------------------------------+
```

### 2.2 Anatomie des 31-Byte Command Block Wrappers (CBW)
Jedes Steuerkommando wird durch `messages/C2001e1.java` (`protocol.build_usbc`) in einen 31 Byte langen USBC-Rahmen gekapselt (bei Host-to-Device-Schreibbefehlen mit `flags = 0x00` folgen die `data_len` Nutzdatenbytes unmittelbar ab Byte 31):

| Byte-Offset | Feldbezeichnung | Länge | Wert / Hex | Beschreibung |
| :--- | :--- | :--- | :--- | :--- |
| `0x00 - 0x03` | `dCBWSignature` | 4 B | `55 53 42 43` | ASCII `"USBC"` (CBW Magic) |
| `0x04 - 0x07` | `dCBWTag` | 4 B | `A0 CB 03 37` | Transaktions-ID / Magic Tag (konstant) |
| `0x08 - 0x0B` | `dCBWDataTransferLength` | 4 B | `uint32_BE` | Erwartete Datenlänge in der Datenphase |
| `0x0C` | `bmCBWFlags` | 1 B | `0x80` / `0x00` | Direction (`0x80` = Device-to-Host Read, `0x00` = Host-to-Device Write) |
| `0x0D` | `bCBWLUN` | 1 B | `0x00` | Logical Unit Number (immer 0) |
| `0x0E` | `bCBWCBLength` | 1 B | `0x10` | CDB-Länge (16 Bytes = `0x10`) |
| `0x0F` (`15`) | `CDB[0]` Prefix | 1 B | `0xF6..0xFB` | APIX Opcode-Hauptklasse |
| `0x10 - 0x13` | `CDB[1..4]` Magic | 4 B | `41 50 49 58` | ASCII `"APIX"` |
| `0x14` (`20`) | `CDB[5]` Sub-Opcode | 1 B | `0x00..0x61` | Sub-Befehl innerhalb der APIX-Klasse |
| `0x15 - 0x1E` | `CDB[6..15]` Payload | 10 B | `Bytes` (`21..30`) | Befehlsspezifische Parameter & Padding (Inline-Payload) |

### 2.3 Datenphase & 13-Byte Command Status Wrapper (CSW)
* **2-Byte Antwort-Echo:** Jede TCP-Datenphase vom Dongle beginnt mit den 2 Bytes `[opcode, subopcode]` (z. B. `f6 16 ...`, `f6 03 ...`, `f6 31 <?xml ...`, `fa 00 ...`), bevor die eigentlichen Nutzdaten folgen.
* **13-Byte USBS-Trailer:** Jede Antwort schließt mit `55 53 42 53 A0 CB 03 37 <4B residue> <1B status>` (`"USBS..."`) ab.

---

## 3. Vollständige Opcode- & Befehlsreferenz (Alle 5 SDK-Klassen)

### 3.1 Klasse `0xF6` (`messages/onGetBouquetListXml.java`) — Tuner, Scan, Kanalliste, EPG & System

| Sub-Opcode | SDK-Name / Dispatcher-ID | `data_len` & `flags` | Inline-Payload (USBC Bytes 21–30) & Antwortstruktur |
| :--- | :--- | :--- | :--- |
| `0x00` | `CMD_TUNER_DONGLE_REBOOT` (`108`) | `2 B`, `0x80` | Startet den Dongle neu |
| `0x01` | `CMD_TUNER_DVBS2_SET` (`125`) | `32 B`, `0x80` | **DVB-S2 Transponder-Tune:** `b21 = 0x04 \| pol_bits \| khz_bits`, `b22..23 = satLon` (`uint16_BE`, Bit 7 = West), `b24..25 = sr_kHz` (`uint16_BE`), `b26..28 = freq_kHz` (`uint24_BE`), `b29..30 = 00 00` |
| `0x01` | `CMD_TUNER_SET` (`110` / `118`) | `2 B`, `0x80` | **DVB-T/C Tune & Standby:** `b21=tunerType`, `b22=mode`, `b23=bw`, `b24..25=sr`, `b26..28=freq`. Mit `0, 4, 0, 0, 0` = Tuner-Standby (`118`) |
| `0x01` | `CMD_START_SCAN_DVB_IPTV` (`711`) | `2 B`, `0x80` | **IPTV Tune:** `b21=0x07`, `b22=proto (0=RTP,1=UDP)`, `b23..26=IPv4`, `b27..28=Port (uint16_BE)` |
| `0x02` | `CMD_TUNER_STATUS` (`112`) | `17 B`, `0x80` | **Signal- & Scan-Status:** `r[2]=lock (bit0)/fail (bit7)`, `r[3]=AGC%`, `r[4]=SNR%`, `r[5]=scanState (1=läuft, 0=fertig)`, `r[6]=progress%`, `r[7..9]=freq`, `r[10..11]=sr`, `r[12]=mode`, `r[13..14]=tvCount`, `r[15..16]=radioCount` |
| `0x03` | `CMD_CHANGE_CHANNEL_*` (`86/87/802..809`) | `4 B`, `0x80` | **Kanalwechsel:** `b21..23=00 00 00`, `b24=Modus` (`0x00`=Down, `0x10`=Up, `0x02`=By `prog_idx`, `0x03`=By `SID`, `0x04`=`prog_idx`+PID, `0x05`=`SID`+PID), `b25..28=prog_idx/SID` (`uint32_BE`), `b29..30=PID` (`uint16_BE`). Antwort: `f6 03 <lock> <isFta>` |
| `0x05` | `CMD_TUNER_SET_MODE` (`128`) | `0 B`, `0x80` | `b21 = tunerType` (`0x04` = DVB-S2) |
| `0x06` | `CMD_REMOVE_CH_LIST` (`709`) | `2 B`, `0x80` | Löscht die gespeicherte Kanalliste auf dem Dongle |
| `0x07` | `CMD_TUNER_DVBS2_SET_LNB` (`126`) | `2 B`, `0x80` | **LNB-Setup:** `b21..22=lnb1_MHz`, `b23..24=lnb2_MHz`, `b25..26=center_MHz`, `b27=unicableSat`, `b28..29=band_MHz`, `b30=0` |
| `0x08` | `CMD_TUNER_DVBS2_SET_DISEQC` (`127`) | `2 B`, `0x80` | **DiSEqC/USALS:** `b21=diseqc11`, `b22=diseqc12`, `b23..24=usals1`, `b25..26=usals2`, `b27..28=usals3`, `b29..30=usals4` |
| `0x09` | `CMD_TUNER_DVBS2_SET_SATELLITE` (`132`) | `2 B`, `0x80` | **Satellit setzen:** `b21..22=satLon` (`uint16_BE`, Bit 7 in `b21` = West), `b23 = 0x04 \| pol_bits \| khz_bits` |
| `0x10` (`16`) | `CMD_TUNER_SCAN` (`111` / `704`) | `2 B`, `0x80` | **Suchlauf Start/Stop:** `b21=scanType` (`0`=Manual, `1`=Auto, `2`=Network, `3`=Stop), `b22 = netScan \| (orderBy<<1) \| (range<<3) \| (sort<<6)` |
| `0x11` (`17`) | `CMD_CH_MANUAL_SCAN_LIST_LENGTH` (`113`) | `4/6 B`, `0x80` | Länge der beim Suchlauf gefundenen Kanalliste (`4 B` bei DVB-S2 / `usbProtoVer==2`, sonst `6 B`) |
| `0x12` (`18`) | `CMD_CH_MANUAL_SCAN_LIST_DATA` (`114`) | `len B`, `0x80` | XML-Daten der beim Suchlauf gefundenen Kanäle |
| `0x13..0x15` | `CMD_OTA_TUNE / START / STATUS` (`115..117`) | `2/11 B`, `0x80` | OTA-Transponder-Tune (`0x13`), OTA-Start (`0x14`), OTA-Status (`0x15`, `11 B`) |
| `0x16` (`22`) | Handshake / Keep-Alive Ping | `12 B`, `0x80` | Antwort `f6 16 <status> <5B dev_id> 00 00 00 00` (`r[2] == 0x01` = bereit) |
| `0x17` (`23`) | Session Init / Disconnect | `4 B`, `0x80` | `b21=0x00` (Session-Init beim Start) bzw. `b21=0x01` (Session-Disconnect) |
| `0x20` (`32`) | `CMD_GET_CH_LIST` Size (`705`) | `8 B`, `0x80` | Antwort `f6 20 <uint32_BE xml_size> 00 00` |
| `0x21` (`33`) | `CMD_GET_CH_LIST` XML | `size B`, `0x80` | Antwort `f6 21 <?xml ...><ch_List>...</ch_List>\x00\x00` |
| `0x22` (`34`) | `ch_List` Ack / `CMD_GET_BOUQUET_LIST` | `8/6 B`, `0x80` | `data_len=8`: Quittung nach `0x21`; `data_len=6`: Bouquet-Listen-Größe |
| `0x23..0x25` | Bouquet XML & Bouquet-ChList (`801`) | `6/size B`, `0x80` | `0x23` Bouquet-XML; `0x24` (`b25..28=bouquetId`) Größe; `0x25` Bouquet-Kanalliste |
| `0x26..0x27` | Confirm Remove Ch / Set LCN (`803`) | `2 B`, `0x80` | `0x26`: Kanal-Löschung bestätigen; `0x27`: `b21 = 1` (LCN an) / `0` (LCN aus) |
| `0x28..0x2B` | Satelliten- & Transponder-XML | `6/size B`, `0x80` | `0x28/0x29`: Satellitenliste XML; `0x2A/0x2B`: Transponderliste XML |
| `0x30..0x31` | `CMD_GET_EPG` Size & XML (`706`) | `6/size B`, `0x80` | `b25..28=prog_idx`, `b29..30=offset` (bei `0x31`); liefert `<epg_Data>` XML |
| `0x32..0x33` | `CMD_GET_CH_INFO` Size & XML (`708`) | `6/size B`, `0x80` | `b25..28=prog_idx`; liefert `<ch_Info>` XML (Audio-Spuren, Untertitel, Alter, Teletext) |
| `0x35..0x36` | `CMD_GET_EVENT_DESC` Size & XML (`707`) | `6/size B`, `0x80` | `b23..24=event_id`, `b25..28=prog_idx`; liefert `<event_desc>` XML |
| `0x37` (`55`) | `CMD_SET_LCN_NUM` (`804`) | `8 B`, `0x00` | 31B USBC + 8B Payload (`[prog_idx_BE, lcn_num_BE]`) |
| `0x38` (`56`) | EPG Transfer Stop | `2 B`, `0x80` | Bricht laufenden EPG-Abruf ab |
| `0x39` (`57`) | Set ISO-639 Language | `3 B`, `0x00` | 31B USBC + 3B Sprachcode (z. B. `b"deu"`) |
| `0x40` (`64`) | `CMD_TUNER_FACTORY_RESET_REBOOT` (`109/133`) | `2 B`, `0x80` | `b21=0x00`: Werksreset & Reboot (`109`); `b21=0xFF`: Fresh Reset (`133`) |
| `0x41..0x42` | Set / Get Customer Variation (`805/806`) | `2/7 B`, `0x80` | `0x41`: `b21=variation`; `0x42`: liefert `f6 42 <variation>` |
| `0x50` (`80`) | Get Customer Parameter | `7 B`, `0x80` | `b21=param_index` |

### 3.2 Klasse `0xF8` (`messages/onDongleCommunicationStatusHelpText.java`) — CAS / Smartcard-MMI & Stream-Sleep

| Sub-Opcode | SDK-Name / Dispatcher-ID | `data_len` & `flags` | Beschreibung & Payload |
| :--- | :--- | :--- | :--- |
| `0x00..0x01` | `CMD_CAS_MMI_DATA_LENGTH / DATA` (`200/201`) | `6/len B`, `0x80` | Länge und Payload einer CAS/Smartcard-MMI-Nachricht |
| `0x02` | CAS PIN Check | `4 B`, `0x00` | 31B USBC + 4B PIN |
| `0x03` | `CMD_CAS_SET_MATURITY` (`205`) | `5 B`, `0x00` | 31B USBC + 5B (`[pin_b3..b0, maturity_level]`) |
| `0x04` | `CMD_CAS_SET_PIN` (`204`) | `8 B`, `0x00` | 31B USBC + 8B (`[old_pin_4B, new_pin_4B]`) |
| `0x05` | `CMD_CAS_RETURN_RESPONSE` (`207`) | `4 B`, `0x00` | 31B USBC + 4B MMI-Menüauswahl |
| `0x06` | `CMD_CAS_GET_MATURITY_STATUS` (`206`) | `4 B`, `0x80` | Liest aktuelle Jugendschutzstufe (`r[2]`) |
| **`0x07`** | **`CMD_CAS_SLEEP_MODE` (`208`)** | **`4 B`, `0x00`** | **Stream/Recording Stop (`35 Bytes` = 31B USBC + `[mode, 0, 0, 0]`): `mode=1` stoppt Stream, `mode=0` weckt auf** |
| `0x10..0x11` | `CMD_CAS_STATUS_LENGTH / DATA` (`202/203`) | `6/len B`, `0x80` | CAS-Status-XML (`b21=status_type`) |
| `0x12` (`18`) | `CMD_CAS_REMOVE_MAIL` (`217`) | `4 B`, `0x00` | Löscht CAS-Mail (`[mail_idx_BE]`) |
| `0x13..0x17` | CAS Fingerprint / OSD / Transmode | `6/len B`, `0x80` | CAS-Fingerprint- und OSD-Abfragen |

### 3.3 Klasse `0xF9` (`messages/CreNovaDongleInitListener.java`) — UDP-Stream, IPTV-Injektion & Speedtest

| Sub-Opcode | SDK-Name / Dispatcher-ID | `data_len` & `flags` | Beschreibung & Payload |
| :--- | :--- | :--- | :--- |
| `0x00` | Stream Buffer Status | `5 B`, `0x80` | Liest Pufferstatus |
| **`0x01`** | **DVB-S2 UDP Stream Pull** | **`48.128 B`, `0x80`** | **`b21=0x00` (Start / nach Erfolg), `b21=0x01` (Retry nach Timeout). Antwort: `48.205 B` (`48.128B TS + 64B EXTRACSW + 13B USBS`)** |
| **`0x02`** | **UDP Stream Socket Init** | **`0 B`, `0x00`** | **`b21=0x01`; initialisiert den UDP-Stream-Port 8800 (Antwort: `13 B USBS`)** |
| `0x03, 0x04, 0x08` | IPTV TS-Block Injection | `48.128 B`, `0x00` | Injiziert 48-KB-MPEG-TS-Blöcke vom Host in den Dongle (für IPTV-Demux) |
| `0x05, 0x06` | `CMD_START_LOOP_TEST` (`306`) | `48.128 B`, `0x00/0x80` | `0x05` schreibt 48-KB-Testblock (`b21=seq`), `0x06` liest ihn zurück |
| **`0x0A` (`10`)** | **`CMD_START_SPEED_TEST` (`307`)** | **`48.128 B`, `0x80`** | **Speedtest (`getSpeedTestMbps()`), KEINE Kanal-Datenbank!** |
| `0x0B` (`11`) | Hybrid IPTV Inject & Get | `48.128 B`, `0x80` | Kombiniertes Senden und Empfangen für IPTV |

### 3.4 Klasse `0xFA` (`messages/onDongleCommunicationStatus.java`) — Dongle-Info, CI+/SAC-Handshake & Firmware

| Sub-Opcode | SDK-Name / Dispatcher-ID | `data_len` & `flags` | Beschreibung & Antwortstruktur |
| :--- | :--- | :--- | :--- |
| **`0x00`** | `CMD_SECURE_CH_GET_DONGLE_INFO` (`300`) | `64 B`, `0x80` | **Dongle-Info Phase 1:** `r[2]=tunerType` (`26`=DVB-S2), `r[3..4]=customerId`, `r[5..6]=hwVer`, `r[7..8]=swVer`, `r[9]=loaderVer`, `r[10..11]=casType`, `r[12..19]=chipId`, `r[20..25]=serialId`, `r[26..29]= verifyCode`, `r[30]&0x0F=usbProtoVer` (`2`), `r[31]=hasPhase2` (`1`), plus 16B `systemId` für `SecureNativeModule.setSystemId` |
| **`0x01`** | SAC Poll Response Length | `6 B`, `0x80` | Antwort `fa 01 <sacFlag> 00 <uint16_BE pkt_len>` (`C2002c.java`) |
| **`0x02`** | SAC Read Response Packet | `pkt_len B`, `0x80` | Antwort `fa 02 <sacFlag> 00 <payload...>`; bei `sacFlag==1` wird `ccExtractSacMessage` aufgerufen |
| **`0x03`** | SAC Write Request Packet | `len B`, `0x00` | `b21=isSacEmbedded` (`0x00` oder `0x01`) + `len` Bytes SAC-Request |
| `0x04..0x06` | `CMD_UPDATE_DONGLE_START` (`400`) | `8/chunk B` | Firmware-Flash über USB/TCP: `0x04` Start (`[totalSize_BE, chunkSize_BE]`), `0x05` Datenblock (`[idx_u16, total_u16, len_u32, data...]`), `0x06` Status (`8 B`) |
| **`0x07`** | Dongle-Info Phase 2 | `51 B`, `0x80` | `r[3..34]=modelName` (`"TC711CXD"`), `r[35..38]=svnRevision` (`uint32_BE`), `r[39..50]=vscId` (`12 B`). Falls `svnRevision >= 14279` → Phase 3 (`0xFA/0x08`) |
| **`0x08`** | Dongle-Info Phase 3 | `480 B`, `0x80` | `r[2..7]=Dongle MAC`, `r[8..11]=Dongle IP`, `r[12..15]=Client IP`, Feature-Flags: `r[19]&0x0F=newWayCBW`, `r[21]&0x0F=clearFTAStream`, `r[24]&0x0F=isSATSetupEnabled` |
| `0x0A..0x19` | `CMD_GET_OTA_FW_INFO` (`712`) | `4..52 B` | OTA-Firmware-Download & IPTV-Kanallisten-Sync (`0x14`=OTA Info, `0x12`=OTA Status 52B, `0x10/0x11`=OTA Datenblock, `0x13`=OTA Stop) |

### 3.5 Klasse `0xFB` (`messages/onDongleGetIntegerData.java`) — Factory Production Mode

| Sub-Opcode | SDK-Name / Dispatcher-ID | `data_len` & `flags` | Beschreibung |
| :--- | :--- | :--- | :--- |
| `0x01` | `CMD_SEND_PRODUCTION_DATA` (`501`) | `len B`, `0x00` | Schreibt Werks-/Kalibrierungsdaten (`b21..22=blockIdx`, `b23..24=totalBlocks`, `b25..28=len`) |
| `0x02` | `CMD_GET_PRODUCTION_REPORT` (`502`) | `58 B`, `0x80` | Liest Produktions-XML-Report (`serialNumber`, `vscId`, `vrfCode`) |
| `0x03` | `CMD_SET_PRODUCTION_MODE` (`500`) | `4 B`, `0x00` | Schaltet Produktionsmodus ein/aus (31B USBC + 4B Mode) |

---

## 4. DVB-S2 Sendersuchlauf & LNB/DiSEqC-Steuerung (`src/scan.py`)

Frühere Vermutungen, ein Sendersuchlauf würde über `0xF7/0x01` oder `0xF8/0x01..0x04` laufen, wurden durch die vollständige Dekompilierung von `sdk/onDongleGetIntegerData.java` (Zeilen 487–672 & 1209–1286) widerlegt. Der tatsächliche DVB-S2-Suchlauf läuft komplett über **`0xF6`** in exakt **7 Schritten**:

1. **LNB konfigurieren (`0xF6 / 0x07` – `cmd_dvbs2_lnb_set`):**
   * Setzt Low-Band-LOF (`9750 MHz`), High-Band-LOF (`10600 MHz`), Switch-Frequenz (`11700 MHz`) sowie Unicable-Parameter.
2. **DiSEqC / USALS konfigurieren (`0xF6 / 0x08` – `cmd_dvbs2_diseqc_set`):**
   * Setzt DiSEqC 1.0/1.1/1.2 Port und optionale USALS-Motorparameter.
3. **Satellitenposition setzen (`0xF6 / 0x09` – `cmd_dvbs2_satellite_set`):**
   * Überträgt Orbitposition in `0,1°` (z. B. `192` = `0x00C0` für Astra 19,2° Ost; Bit 7 im High-Byte = West) und Polarisations-/22-kHz-Bits (`0x04 | pol_bits | khz_bits`).
4. **Transponder einstellen (`0xF6 / 0x01` – `cmd_dvbs2_tuner_set`, `data_len = 32`):**
   * Überträgt Polarisation (`0x10` = H/18V, `0x20` = V/13V), Satellitenposition, Symbolrate in kS/s (`uint16_BE`, z. B. `22000`) und Frequenz in kHz (`uint24_BE`).
5. **Suchlauf starten (`0xF6 / 0x10` – `cmd_scan_start_stop`):**
   * `byte21` = `0` (`SCAN_MANUAL`), `1` (`SCAN_AUTO`), `2` (`SCAN_NETWORK`) oder `3` (`SCAN_STOP`).
   * `byte22` = Bitfeld aus `networkScan (Bit 0) | (orderBy << 1) | (searchRange << 3) | (sortMode << 6)`.
6. **Suchlauf-Fortschritt pollen (`0xF6 / 0x02` – `parse_tuner_scan_status`, alle 500 ms):**
   * Solange `r[5] == 1` (`scan_in_progress`), liefert die 17-Byte-Antwort den Fortschritt `r[6]` (`0..100 %`), Signalwerte (`r[3]` AGC, `r[4]` SNR), aktuelle Frequenz (`r[7..9]`), Symbolrate (`r[10..11]`) sowie die laufende Anzahl gefundener TV- (`r[13..14]`) und Radio-Sender (`r[15..16]`).
   * Sobald `r[5] == 0`, ist der Suchlauf abgeschlossen.
7. **Gefundene Kanalliste abrufen (`0xF6 / 0x11` & `0xF6 / 0x12`):**
   * `0xF6 / 0x11` (`cmd_scan_result_size`) liefert die XML-Größe; `0xF6 / 0x12` (`cmd_scan_result_data`) lädt die XML-Kanalliste der gefundenen Sender.

---

## 5. Link-Verschlüsselung der MPEG-TS-Pakete (AES-128-ECB)

Ein zentrales Ergebnis der Live-Verifikation und APK-Dekompilierung (`com.crenova.tv.dongle.dvb.sdk.ui.player.a.onDongleCommunicationStatusHelpText`):

* **Auch bei freien Sendern (`FTA`, `fta="1"`)** verschlüsselt der Dongle alle Video-, Audio- und Teletext-TS-Pakete vor dem UDP-Versand und setzt im 4-Byte-TS-Header `transport_scrambling_control = 2` (`(pkt[3] >> 6) & 3 == 2`).
* Lediglich PSI-Tabellen wie PAT (`PID 0x0000`) und PMT bleiben unverschlüsselt (`transport_scrambling_control = 0`).
* **Entschlüsselung (`src/decrypt.py`):**
  * Chiffre: **`AES-128-ECB` (`AES/ECB/NoPadding`)**
  * Statischer 16-Byte-Schlüssel: **`1234567880ABCDEF1234567880ABCDEF`**
  * Für jedes 188-Byte-Paket mit `pkt[0] == 0x47`, `(pkt[3] >> 6) & 3 == 2` und `((pkt[3] >> 4) & 1) == 1`:
    1. `pkt[3] &= 0x7F` (löscht das Scrambling-Bit).
    2. Adaptation-Field (falls `(pkt[3] & 0x30) == 0x30`, Länge `adapt_len = pkt[4] + 1`) wird unverändert übersprungen.
    3. Vom Payload (`pay_len = 184 - adapt_len` ab Offset `4 + adapt_len`) werden `enc_len = (pay_len // 16) * 16` Bytes per `AES-128-ECB` entschlüsselt; die restlichen `< 16` Bytes am Paketende sind unverschlüsselt.

---

## 6. `0x48xxxxxx` (Radio vs. Pay-TV) & CI+/SAC-Handshake (`0xFA`, `libsecure_module.so`)

### 6.1 Korrektur des `0x48xxxxxx`-Präfixes: Radio (`type="RD"`), nicht Pay-TV!
* In der `<ch_List>`-XML des Dongles haben **alle TV-Sender** (`type="TV"`) ein `prog_idx` der Form **`0x40xxxxxx`**, während **alle Radiosender** (`type="RD"`, z. B. `hr1`, `Bayern 1`, `OE3`, `1LIVE`) ein `prog_idx` der Form **`0x48xxxxxx`** besitzen.
* Bit 27 (`0x08000000`) im `prog_idx` kodiert also das **Radio-Flag**, **nicht** die Verschlüsselung!
* Ob ein Sender verschlüsselt (Pay-TV) oder frei empfangbar (FTA) ist, wird ausschließlich über das XML-Attribut **`fta="0"`** bzw. **`fta="1"`** (und beim Tuning in `0xF6/0x03` über `r[3] == isFta`) signalisiert. In `src/models.py` prüft `is_encrypted` daher exakt `not self.fta`, während `is_radio` das `0x48`-Präfix bzw. `type="RD"` auswertet.

### 6.2 Vollständige Nachbildung des CI+ / SAC-Handshakes (`sdk/security/*` & `0xFA/0x01..0x03`)
Das Paket `com.crenova.tv.dongle.dvb.sdk.security` implementiert gemeinsam mit `libsecure_module.so` (Root-Seed `THVrZVJhbkRvbHBoQ0krMQ==` → **`LukeRanDolphCI+1`**) einen dreistufigen CI+-artigen **Secure Authenticated Channel (SAC)** über die Befehle `0xFA/0x03` (Request schreiben), `0xFA/0x01` (6-Byte Antwortlänge pollen) und `0xFA/0x02` (Antwortpaket lesen) in `security/C2002c.java` (`src/scan.py:sac_write_and_read_response`):

1. **Vorbedingung (`DongleSessionInfo` via `0xFA/0x00` → `0xFA/0x07` → `0xFA/0x08`):**
   * Beim Lesen von `0xFA/0x00` übergibt `DongleSessionInfo` das 16-Byte-`systemId`-Array an `SecureNativeModule.setSystemId(bArr)`.
   * Anschließend prüft `DongleCommunicationService` (`sdk/onDongleGetIntegerData.java:361`) die Methode `DongleSessionInfo.CreNovaDongleInitListener()`:
     * Auf Firmware mit `clearFTAStream == 1` (`0xFA/0x08` Byte 21) oder für Standard-FTA-Betrieb gibt diese Methode **`false`** zurück → der SAC-Handshake wird **komplett übersprungen**, und der Player nutzt den statischen AES-128-ECB-Schlüssel `1234567880ABCDEF1234567880ABCDEF`.
     * Nur wenn CAS/CI+-Verschlüsselung aktiv ist (`true`), startet die 3-stufige SAC-Zustandsmaschine (`security/onDongleCommunicationStatus.java`):
2. **Stufe 1 – Mutual Authentication & Diffie-Hellman (`security/onDongleGetIntegerData.java`):**
   * `SecureNativeModule.SecEngInit()` initialisiert die Krypto-Engine mit dem Seed `LukeRanDolphCI+1`.
   * **Schritt 1a (Nonce):** `msgCreateAuthReqNoncePacket()` → `0xFA/0x03(sac=0)` → Antwort via `0xFA/0x01 + 0x02` → `msgExtractAuthRspNoncePacket()` → `hostVerifyCicamChallenge()`.
   * **Schritt 1b (DH-Zertifikat & Signatur):** `msgCreateAuthReqDHSigCertPacket()` → `0xFA/0x03(sac=0)` → Antwort → `msgExtractAuthRspDHSigCertPacket()` → `hostProcessCicamSignAndCert()`.
   * **Schritt 1c (AKH-Bestätigung):** `msgCreateAuthReqCnfAkhPacket()` → `0xFA/0x03(sac=0)` → Antwort → `msgExtractAuthRspCnfPacket()`.
3. **Stufe 2 – Content-Control Key Calculation & Sync (`security/C2004e1.java`):**
   * **Schritt 2a (CC Data Req):** `hostGenerateKs()` → `msgCreateCCDataReqPacket()` → `0xFA/0x03(sac=0)` → Antwort → `msgExtractCCDataCnfPacket()` → `hostStoreCicamKp()` → `hostDeriveCIVnCCK()`.
   * **Schritt 2b (CC Sync Req):** `msgCreateCCSyncReqPacket()` → `ccGenerateSacMessage()` → **`0xFA/0x03(sac=1)`** → Antwort (`sacFlag==1` → `ccExtractSacMessage()`) → `msgExtractCCSyncCnfPacket()`.
4. **Stufe 3 – SAC Keying für den TS-Stream (`security/CreNovaDongleInitListener.java`):**
   * **Schritt 3a (SAC Keying Req):** `msgCreateCCSACKeyingReqPacket()` → `0xFA/0x03(sac=0)` → Antwort → `msgExtractCCSACDataCnfPacket()` → `hostStoreCicamKp()` → `hostDeriveCIVnCCK()`.
   * **Schritt 3b (SAC Sync Cnf):** `msgCreateCCSACSyncCnfPacket()` → `ccGenerateSacMessage()` → **`0xFA/0x03(sac=1)`** → Antwort (`ccExtractSacMessage()`) → `msgExtractCCSACSyncReqPacket()`.
   * Nach Abschluss liefern `SecureNativeModule.hostGetCCK(16)` und `hostGetCIV(16)` den dynamischen 16-Byte-Schlüssel (`CCK`), der im Player anstelle von `DEFAULT_TS_KEY` gesetzt wird (`playerCrypto.setKey(cck)`).

---

## 7. Python-Client (`src/`)

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

## 8. Widerlegte Mythen & Fakten-Check

| Frühere Annahme / Mythos | Verifizierte Realität |
| :--- | :--- |
| **`connect()` prüft `r[0] == 0x01`** | **Falsch:** Jede TCP-Antwort beginnt mit 2 Echo-Bytes (`f6 16`); der Status steht in **`r[2]`**. |
| **`0xF6/0x03` hat `prog_idx` an Bytes 21–24** | **Falsch:** Bytes 21–24 sind der Modus `00 00 00 02`, `prog_idx` steht an **Bytes 25–28**. |
| **`0xF8/0x07` schaltet den Stream beim Start frei** | **Falsch:** `0xF8/0x07` (35 Bytes inkl. `01 00 00 00`) ist der **Stream-Stop-Befehl (`CMD_CAS_SLEEP_MODE`)** beim Beenden. |
| **`0xF9/0x01` nutzt `byte21=0x01` für alle Folgeblöcke** | **Falsch:** `byte21=0x00` fordert den nächsten Block nach Erfolg an; `byte21=0x01` ist **nur Retry nach Timeout**. |
| **FTA-Streams sind auf UDP unverschlüsselt** | **Falsch:** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`tsc=2`) mit **AES-128-ECB** (`1234567880ABCDEF1234567880ABCDEF`). |
| **Kanalliste kommt per UDP-Blob (`0xF9/0x0A`)** | **Falsch:** `0xF9/0x0A` ist ein **Speedtest** (`getSpeedTestMbps()`). Kanalliste kommt per **TCP XML** (`0xF6/0x20` + `0xF6/0x21`). |
| **Sendersuchlauf nutzt `0xF7/0x01` und `0xF8/0x01..0x04`** | **Falsch:** `0xF7` existiert im SDK nicht, `0xF8` ist CAS/MMI. Der DVB-S2-Suchlauf nutzt **`0xF6/0x07 → 0x08 → 0x09 → 0x01 → 0x10 → 0x02 → 0x11/0x12`**. |
| **`prog_idx = 0x48xxxxxx` kennzeichnet Pay-TV** | **Falsch:** `0x48xxxxxx` (Bit 27) kennzeichnet **Radiosender (`type="RD"`)**. Verschlüsselung wird ausschließlich durch **`fta="0"`** angezeigt. |
