# WISI OR S2D — Vollständige Stream-Spezifikation (A bis Z)

**Dokument-Typ:** Verifizierte technische Ablauf- & Protokollspezifikation (Stand: November 2026)  
**Geltungsbereich:** WISI OR S2D (TiViCon / Schwaiger DSRD0100)  
**Ziel:** Exakte, gegen PCAPs, dekompiliertes APK und Live-Hardware verifizierte Anleitung von Verbindungsaufbau, Tuning, UDP-Pulling, Link-Entschlüsselung (FTA vs. Pay-TV) bis zum Verbindungsabbau.

---

## 1. Architektur-Überblick & Socket-Rollen

Die Kommunikation mit dem Dongle ist in zwei Kanäle aufgeteilt:

1. **Steuerkanal (TCP Port 8802):**
   * Protokoll: 31-Byte USBC-Command-Block-Wrapper (CBW) / 13-Byte USBS-Status-Wrapper (CSW).
   * Jede Antwort des Dongles beginnt in der Datenphase mit einem 2-Byte-Echo `[opcode, subopcode]`, gefolgt von den Befehlswerten und abgeschlossen durch den 13-Byte-`USBS`-Trailer.
   * Rolle: Session-Handshake, Kanallisten-Abruf (XML), Kanalwechsel (`0xF6/0x03`), Signal-/EPG-Abfragen und Stream-Stop (`0xF8/0x07`).
2. **Datenkanal (UDP Port 8800):**
   * Protokoll: UDP-Datagramme mit 31-Byte USBC-Pull-Requests (`0xF9/0x01`).
   * Rolle: Aktives Anfordern (Pulling) und Empfangen der MPEG-Transport-Stream-Blöcke (`48.205 Bytes` pro Antwort).

---

## 2. Phase 1: Verbindungsaufbau & Handshake (`connection.py`)

### Schritt 1.1: Sockets öffnen
* **TCP-Client-Socket:** Verbinde zu `DONGLE_IP:8802`.
* **UDP-Client-Socket:** Binde lokal auf Port `8800` mit ausreichendem Empfangspuffer (`SO_RCVBUF >= 64 KiB`, im Client `8 MiB`) und `500 ms` Timeout.

### Schritt 1.2: Handshake-Sequenz (TCP 8802)
1. **Status-Abfrage (`0xF6 / 0x16`):**
   * Sendet 31-Byte CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x16`, `data_len = 12`, `flags = 0x80`.
   * Antwort (12 Bytes + 13 B USBS): `f6 16 <status> <5B device_id> 00 00 00 00`.
   * Auf einer frischen Verbindung ist `r[2]` zunächst `0x00`.
2. **Session-Init (`0xF6 / 0x17`):**
   * Sendet 31-Byte CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x17`, `data_len = 4`, `flags = 0x80`, `byte21 = 0x00`.
   * Antwort (4 Bytes + 13 B USBS): `f6 17 00 00`.
3. **Bereitschaftspoll (`0xF6 / 0x16`):**
   * Falls `status != 0x01` war, wird `0xF6 / 0x16` erneut gesendet; direkt nach `0xF6 / 0x17` meldet `r[2] == 0x01` (Dongle bereit).

---

## 3. Phase 2: Kanalwechsel & Signalprüfung (`prepare.py`)

Sender werden beim Umschalten über ihren 32-Bit **`prog_idx`** aus der XML-Kanalliste (`0xF6/0x20+0x21`) adressiert.

### Schritt 2.1: Kanal umschalten (`0xF6 / 0x03` – `cmd_prepare`)
* **Request:** 31-Byte CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x03`, `data_len = 4`, `flags = 0x80`.
* **Payload (USBC Bytes 21–28):**
  * Bytes `21..24`: `00 00 00 02` (Modus `2` = `ACTION_CHANGE_CHANNEL_BY_PROGIDX`)
  * Bytes `25..28`: `prog_idx` als `uint32_BE` (z. B. `40 DE 01 10` für RTL Austria)
* **Response (4 Bytes + 13 B USBS):** `f6 03 <signalLock> <isFta>`.
  * Falls `signalLock == 0`, bis zu 3× im Abstand von `250 ms` wiederholen.

### Schritt 2.2: Kanal-Metadaten & Signal-Check
1. **Kanal-Info abrufen (`0xF6 / 0x32` & `0xF6 / 0x33`):**
   * `0xF6 / 0x32` (`data_len = 6`, Bytes `25..28` = `prog_idx`): liefert `f6 32 <uint32_BE xml_len>`.
   * `0xF6 / 0x33` (`data_len = xml_len`, Bytes `25..28` = `prog_idx`): liefert `f6 33 <?xml ...><ch_Info>...</ch_Info>\x00\x00`.
2. **Signal-Polling (`0xF6 / 0x02`):**
   * `data_len = 17`, Antwort `f6 02 <lock> <strength_%> <quality_%> ...` (`r[3]` = Stärke in %, `r[4]` = Qualität in %).

---

## 4. Phase 3: Der UDP-Streaming-Loop (`stream.py`)

```text
 Client (Python)                                      WISI OR S2D Dongle
     |                                                       |
     |--------------- TCP 0xF6/0x03 (Tune prog_idx) -------->|
     |<-------------- TCP f6 03 01 01 (Lock=1, FTA=1) -------|
     |--------------- UDP 0xF9/0x02 (UDP Init) ------------->|
     |<-------------- UDP 13 B USBS -------------------------|
     |                                                       |
     |  +-------------------------------------------------+  |
     |  | LOOP:                                           |  |
     |  | 1. UDP 0xF9/0x01 (byte21=0x00 normal /          |  |
     |  |                   byte21=0x01 nach Timeout) --->|  |
     |  | 2. UDP 48.205 B (48.128B TS + 64B EXTRACSW      |  |
     |  |                  + 13B USBS) <------------------|  |
     |  | 3. Prüfe EXTRACSW[12] (Block-Sequenz 0..255)    |  |
     |  | 4. Schreibe 48.128 B (256 × 188B TS-Pakete)     |  |
     |  | 5. TCP 0xF6/0x16 (Keep-Alive alle 2s) --------->|  |
     |  | 6. TCP 0xF6/0x02 (Signal-Poll alle 3s) -------->|  |
     |  +-------------------------------------------------+  |
     |                                                       |
     |--------------- TCP 0xF8/0x07 (35B Stream Stop) ------>|
```

### Schritt 3.1: UDP-Initialisierung (`0xF9 / 0x02`)
* Einmaliges Senden von `0xF9 / 0x02` (`data_len = 0`, `flags = 0x00`, `byte21 = 0x01`) an `DONGLE_IP:8800`. Der Dongle antwortet mit einem 13-Byte `USBS`-Paket.

### Schritt 3.2: Die Pull-Schleife (`0xF9 / 0x01`)
* **Request:** 31-Byte CBW mit `Opcode = 0xF9`, `Sub-Opcode = 0x01`, `data_len = 0xBC00` (`48.128`), `flags = 0x80`.
* **Bedeutung von Byte 21 (`retry_last` / `getCustomerVariation` im APK):**
  * **`byte21 = 0x00`**: Beim allerersten Pull **und nach jedem erfolgreich empfangenen Block** (fordert den nächsten Block an).
  * **`byte21 = 0x01`**: **Nur nach einem UDP-Timeout (500 ms) oder verworfenen Block** (fordert denselben Block erneut an, nach `10 ms` Pause).
* **Antwortformat (`48.205 Bytes`):**
  * Bytes `0 .. 48127` (`48.128 Bytes`): Exakt **256 MPEG-TS-Pakete à 188 Bytes** (jeweils beginnend mit Sync-Byte `0x47`).
  * Bytes `48128 .. 48191` (`64 Bytes`): `EXTRACSW`-Block (`"EXTRACSW"` + Metadaten; Byte `12` = `data[48140]` ist der laufende 8-Bit-Blockzähler `0..255`).
  * Bytes `48192 .. 48204` (`13 Bytes`): `USBS`-Status-Trailer.

---

## 5. Verschlüsselung & Entschlüsselung (`decrypt.py`)

### 5.1 Link-Verschlüsselung des Dongles (betrifft ALLE Sender, auch FTA!)
* **Wichtiger Befund:** Obwohl FTA-Sender (`fta="1"`, `prog_idx = 0x40xxxxxx`) über Satellit unverschlüsselt ausgestrahlt werden, **verschlüsselt der WISI-Dongle selbst** alle Video-, Audio- und Teletext-TS-Pakete vor dem UDP-Versand und setzt im TS-Header `transport_scrambling_control = 2` (`(pkt[3] >> 6) & 3 == 2`). Lediglich PSI/SI-Tabellen wie PAT (`PID 0x0000`) und PMT bleiben unverschlüsselt.
* **Algorithmus laut APK (`com.crenova.tv.dongle.dvb.sdk.ui.player.a.onDongleCommunicationStatusHelpText`):**
  * Chiffre: **`AES-128-ECB` (`AES/ECB/NoPadding`)**
  * Statischer 16-Byte-Schlüssel: **`1234567880ABCDEF1234567880ABCDEF`**
  * Verarbeitung pro 188-Byte-TS-Paket (`pkt[0] == 0x47`):
    1. Prüfe `scram = (pkt[3] >> 6) & 3` und `has_payload = ((pkt[3] >> 4) & 1) == 1`.
    2. Falls `scram == 2` und `has_payload`:
       * Lösche Bit 7 in Byte 3: `pkt[3] &= 0x7F` (setzt `transport_scrambling_control` auf `0`).
       * Falls ein Adaptation-Field existiert (`(pkt[3] & 0x30) == 0x30`), bestimme dessen Länge `adapt_len = pkt[4] + 1` (sonst `0`) und lasse das Adaptation-Field unverändert.
       * Berechne den Payload-Offset `pay_off = 4 + adapt_len` und die Payload-Länge `pay_len = 184 - adapt_len`.
       * Entschlüssele `enc_len = (pay_len // 16) * 16` Bytes ab `pay_off` mit `AES-128-ECB`.
       * Die verbleibenden `pay_len - enc_len` Bytes (`0..15` Bytes am Ende des TS-Pakets) sind unverschlüsselt und bleiben unverändert.
    3. Andernfalls: `pkt[3] &= 0x3F`.
* **Nutzung im Python-Client:**
  * Automatisch am Ende von `--stream` durch Angabe von `--decrypt`, oder
  * Nachträglich für jede gespeicherte `.ts`-Datei per `python src/wisi/decrypt.py stream.ts` bzw. `python src/wisi/wisi.py --decrypt-ts stream.ts`.

### 5.2 `0x48xxxxxx` (Radio vs. Pay-TV) & CI+/SAC-Handshake (`0xFA/0x01..0x03`, `scan.py`)
* **Bedeutung von `0x48xxxxxx`:** In `<ch_List>` haben TV-Sender (`type="TV"`) das Präfix `0x40xxxxxx` und Radiosender (`type="RD"`) das Präfix `0x48xxxxxx` (Bit 27 = `0x08000000`). Verschlüsselung (Pay-TV) wird ausschließlich über **`fta="0"`** angezeigt!
* **CI+ / SAC-Handshake (`com.crenova.tv.dongle.dvb.sdk.security.*` & `libsecure_module.so`):**
  * Beim Abruf von `0xFA/0x00` (`cmd_dongle_info_phase1`) übergibt das SDK die 16-Byte-`systemId` an `SecureNativeModule.setSystemId(bArr)`.
  * Auf FTA-Firmware (`clearFTAStream == 1` in `0xFA/0x08` Byte 21) gibt `DongleSessionInfo.CreNovaDongleInitListener()` `false` zurück; der SAC-Handshake wird übersprungen und der statische Schlüssel `DEFAULT_TS_KEY` genutzt.
  * Bei aktivem CAS/CI+ durchläuft das SDK über `0xFA/0x03` (Write) → `0xFA/0x01` (Poll 6-Byte Len) → `0xFA/0x02` (Read Packet) drei Stufen (`SecEngInit` mit Root-Seed `LukeRanDolphCI+1`):
    1. **Mutual Auth & Diffie-Hellman (`onDongleGetIntegerData.java`):** Nonce-Austausch (`msgCreateAuthReqNoncePacket`), DH-Zertifikat (`msgCreateAuthReqDHSigCertPacket`) und AKH-Bestätigung (`msgCreateAuthReqCnfAkhPacket`).
    2. **Content-Control Key Calculation & Sync (`C2004e1.java`):** `msgCreateCCDataReqPacket` → `hostStoreCicamKp` → `hostDeriveCIVnCCK`, gefolgt von `msgCreateCCSyncReqPacket` (`sac_embedded = 1`).
    3. **SAC Keying für den TS-Stream (`CreNovaDongleInitListener.java`):** `msgCreateCCSACKeyingReqPacket` → `hostDeriveCIVnCCK` → `msgCreateCCSACSyncCnfPacket` (`sac_embedded = 1`) → `hostGetCCK(16)` liefert den dynamischen 16-Byte-AES-Schlüssel.

---

## 6. Phase 4: Stream beenden & Teardown

1. **Stream im Dongle stoppen (`0xF8 / 0x07` – `cmd_stream_release`):**
   * Sendet 35 Bytes über TCP Port 8802: 31-Byte USBC-Header (`data_len = 4`, `flags = 0x00`, `Opcode = 0xF8`, `Sub-Opcode = 0x07`) + 4-Byte Host-to-Device Payload `01 00 00 00`, gefolgt vom Lesen des 13-Byte `USBS`-Trailers.
2. **Keep-Alive-Thread stoppen und UDP/TCP-Sockets schließen.**
3. **Optional (`--decrypt`):** Gespeicherte `.ts`-Datei mit `decrypt_ts_file()` entschlüsseln.
