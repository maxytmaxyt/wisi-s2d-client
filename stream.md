# WISI OR S2D — Vollständige Stream-Spezifikation (A bis Z)

**Dokument-Typ:** Technische Ablauf- & Protokollspezifikation  
**Geltungsbereich:** WISI OR S2D (TiViCon / Schwaiger DSRD0100)  
**Ziel:** Detaillierte Anleitung von Verbindungsaufbau, Tuning, UDP-Pulling, Entschlüsselung (FTA vs. Pay-TV) bis zum geordneten Verbindungsabbau.

---

## 1. Architektur-Überblick & Socket-Rollen

Die Kommunikation mit dem Dongle ist in zwei orthogonale Kanäle aufgeteilt:

1. **Steuerkanal (TCP Port 8802):**
   * Protokoll: 31-Byte USBC-Command-Block-Wrapper (CBW) / 13-Byte USBS-Status-Wrapper (CSW).
   * Rolle: Initialisierung, Session-Handshake, Kanallisten-Abruf (XML), Tuner-Parametrierung und Stream-Freigabe.
2. **Datenkanal (UDP Port 8800):**
   * Protokoll: UDP-Datagramme mit proprietären USBC-Pull-Requests.
   * Rolle: Aktives Anfordern (Pulling) und Empfangen der rohen MPEG-Transport-Streams (MPEG-TS).

---

## 2. Phase 1: Verbindungsaufbau & Handshake

Bevor gestreamt werden kann, müssen TCP- und UDP-Sockets initialisiert werden.

### Schritt 1.1: Sockets öffnen
* **TCP-Client-Socket:** Verbinde zu `DONGLE_IP:8802`.
* **UDP-Client-Socket:** Binde lokal auf Port `8800` (wichtig: muss gebunden sein, bevor Befehle gesendet werden).

### Schritt 1.2: Handshake-Sequenz (TCP 8802)
1. **Status-Abfrage / Handshake Phase 1 (`0xF6 / 0x16`):**
   * Sendet 31-Byte CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x16`, `data_len = 12`.
   * Der Dongle antwortet mit 12 Bytes + CSW.
   * **Prüfung:** Erst wenn Byte `[0]` der Antwort den Wert `0x01` annimmt, ist der Dongle bereit.
2. **Bereitschaftsbestätigung Phase 2 (`0xF6 / 0x17`):**
   * Sendet CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x17`, `data_len = 4`.
   * Bestätigt den Abschluss der Session-Initialisierung.

---

## 3. Phase 2: Kanalauswahl & Tuner-Aktivierung

Sender werden über ihren internen **16-Bit Channel Index** (`pat_idx` bzw. `lcn`) oder den 32-Bit `prog_idx` adressiert.

### Schritt 2.1: Kanal vorbereiten (`0xF6 / 0x03`)
* **Request:** CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x03`.
* **Payload (Bytes 21–24):** 32-Bit `prog_idx` des Senders (z. B. `0x40100004` für FTA).

### Schritt 2.2: Kanal-Metadaten & Signal-Check
1. **Kanal-Info abrufen (`0xF6 / 0x32` & `0xF6 / 0x33`):**
   * Liest XML-Metadaten (`<ch_Info>`) zum aktuellen Transponder.
2. **Signal-Polling (`0xF6 / 0x02`):**
   * Liest Signalstärke (Byte `[1]` %) und Signalqualität (Byte `[2]` %).

### Schritt 2.3: Kanal aktivieren / Tune (`0xF6 / 0x01`)
* **Request:** CBW mit `Opcode = 0xF6`, `Sub-Opcode = 0x01`.
* **Payload (Bytes 21–22):** 16-Bit Kanal-Index als Big-Endian integer.
  * *Beispiel (Kanal-Index 4 = ZDF HD):* `payload[0] = 0x00`, `payload[1] = 0x04`.

### Schritt 2.4: Stream-Freigabe (`0xF8 / 0x07`)
* **Request:** CBW mit `Opcode = 0xF8`, `Sub-Opcode = 0x07`.
* Schaltet den internen Demuxer des Dongles frei, so dass MPEG-TS Daten an den UDP-Puffer weitergeleitet werden.

---

## 4. Phase 3: Der UDP-Streaming-Loop (MPEG-TS Pulling)

Der Dongle sendet Daten nicht ungefragt (Push), sondern erfordert eine kontinuierliche **Pull-Schleife** über UDP Port 8800.

```
 Client (PC/ESP32)                                    WISI OR S2D Dongle
     |                                                       |
     |--------------- UDP 0xF9/0x02 (Init) ----------------->|
     |--------------- UDP 0xF9/0x01 (Pull, byte21=0x00) ---->|
     |<-------------- UDP MPEG-TS Chunk (32.740 Bytes) -----|
     |--------------- TCP 0xF6/0x17 (Tune Ack) ------------->|
     |                                                       |
     |  +-------------------------------------------------+  |
     |  | LOOP:                                           |  |
     |  | 1. UDP 0xF9/0x01 (Pull, byte21=0x01) ---------> |  |
     |  | 2. Receive 32.740 Bytes MPEG-TS Chunk <-------  |  |
     |  | 3. Parse & Align 188-byte TS Packets (Sync 0x47)|  |
     |  | 4. TCP 0xF6/0x16 (Keep-Alive alle 2s) --------> |  |
     |  +-------------------------------------------------+  |
```

### Schritt 3.1: Erste Pull-Initalisierung
1. **UDP Socket-Init (`0xF9 / 0x02`):** Sendet ein kurzes UDP-Signal an Port 8800.
2. **Erster DVB-Pull (`0xF9 / 0x01`):**
   * UDP-Request mit `data_len = 0xBC00` (48.128 Bytes).
   * **Byte 21 = `0x00`** (signalisiert den ersten Block).
3. **TCP-Tune-Bestätigung:**
   * Über TCP Port 8802 wird `0xF6 / 0x17` mit Payload `[0x01, 0x00, 0x00, 0x00]` gesendet.

### Schritt 3.2: Die fortlaufende Pull-Schleife
In einer Schleife sendet der Client fortlaufend:
* **UDP-Pull (`0xF9 / 0x01`):**
  * **Byte 21 = `0x01`** (signalisiert Folgebefehle).
* **Empfang des Datenblocks:**
  * Der Dongle antwortet über UDP mit einem Block von ca. **32.740 Bytes**.
  * Der Block enthält einen 28-Byte Kopf/Trailer-Rahmen und **174 DVB MPEG-TS Pakete à 188 Bytes**.

### Schritt 3.3: Paket-Ausrichtung (Sync-Byte `0x47`)
1. Durchsuche den empfangenen UDP-Puffer nach dem Sync-Byte **`0x47`**.
2. Stelle sicher, dass das nächste `0x47` genau **188 Bytes** später liegt.
3. Extrahiere die 188-Byte-Pakete und leite sie an den Video-Player (z. B. VLC / FFmpeg / Pipe) weiter.

### Schritt 3.4: Keep-Alive Heartbeat
* Um ein Shutdown des Streams zu verhindern, sendet der Client alle 1–2 Sekunden auf dem TCP-Kanal den Heartbeat-Befehl **`0xF6 / 0x16`**.

---

## 5. Verschlüsselung & Entschlüsselung (FTA vs. Pay-TV)

### 5.1 Free-To-Air (FTA) — Kein Aufwand
* **Erkennung:** In der XML-Kanalliste steht `fta="1"`. Der `prog_idx` hat das Präfix `0x40xxxxxx`.
* **Verarbeitung:** **Keine Entschlüsselung erforderlich!** Die vom Dongle gelieferten MPEG-TS-Pakete sind im Klartext und können direkt abgespielt oder gespeichert werden.

### 5.2 Pay-TV / Verschlüsselte Sender (CAS)
* **Erkennung:** In der Kanalliste steht `fta="0"`. Der `prog_idx` hat das Präfix `0x48xxxxxx`.
* **Architektur in der Android-App:**
  * Das SDK nutzt native C/C++ Bibliotheken (`libsecure_module.so`, `libpimbridge.so`, `libpimdec.so`).
  * Die Kommunikation läuft über das Java Native Interface (JNI).

#### Ablauf der Pay-TV-Entschlüsselung:
1. **Root-Seed / Master-Key:**
   * In `libsecure_module.so` ist der Base64-Key `THVrZVJhbkRvbHBoQ0krMQ==` hinterlegt.
   * Dekodiert: **`LukeRanDolphCI+1`**.
2. **Session-Authentication (SAC / CC):**
   * Es wird ein Diffie-Hellman Key Exchange zwischen der App und dem CAS-Modul im Dongle durchgeführt.
3. **ECM / EMM Verarbeitung:**
   * Der Dongle sendet Entitlement Control Messages (ECM) über den Stream.
   * Die native Bibliothek berechnet mittels des Session-Keys die Control Words (CW_EVEN / CW_ODD).
4. **DVB-CSA Descrambling:**
   * Die verschlüsselten TS-Pakete (Payload Scrambling Control Bits `10` oder `11` im TS-Header) werden im Speicher mit den errechneten Control Words entschlüsselt, bevor sie an die Wiedergabe-Pipe übergeben werden.

---

## 6. Phase 4: Stream beenden & Teardown

Um den Dongle sauber zu hinterlassen und Ressourcen freizugeben, muss beim Beenden folgende Sequenz durchlaufen werden:

### Schritt 4.1: Stream stoppen (TCP 8802)
* **Befehl `0xFB / 0x01`:**
  * CBW mit `Opcode = 0xFB`, `Sub-Opcode = 0x01`.
  * **Payload (Byte 21):** `0x00` (Disable Stream).
  * Weist den Dongle an, die Ausgabe auf UDP Port 8800 sofort einzustellen.

### Schritt 4.2: Sockets schließen
1. **UDP-Pull-Schleife abbrechen:** Keine weiteren `0xF9 / 0x01` Anfragen mehr senden.
2. **UDP-Socket schließen:** Port 8800 freigeben.
3. **TCP-Socket schließen:** Verbindung auf Port 8802 trennen.
4. **Puffer leeren:** Arbeitsspeicher leeren.

---

## 7. Zusammenfassende Checkliste für eigene Implementierungen

| Schritt | Kanal | Opcode | Payload / Aktion | Erwartetes Ergebnis |
| :--- | :--- | :--- | :--- | :--- |
| **1. Connect** | TCP | - | Connect to `IP:8802` & Bind UDP `8800` | Sockets bereit |
| **2. Init** | TCP | `0xF6 / 0x16` | `data_len = 12` | Status `0x01` (Ready) |
| **3. Prepare** | TCP | `0xF6 / 0x03` | `prog_idx` (4 Bytes) | Tuner fokussiert |
| **4. Tune** | TCP | `0xF6 / 0x01` | Channel-Index (2 Bytes Big-Endian) | Transponder gelockt |
| **5. Enable** | TCP | `0xF8 / 0x07` | Stream-Freigabe | Demux geöffet |
| **6. Start Pull**| UDP | `0xF9 / 0x01` | `byte21 = 0x00` (First Block) | Erster TS-Puffer empfangen |
| **7. Pull-Loop** | UDP | `0xF9 / 0x01` | `byte21 = 0x01` (Continuous) | MPEG-TS Stream im Takt |
| **8. Heartbeat**| TCP | `0xF6 / 0x16` | Alle 2 Sek. | Verbindung bleibt aktiv |
| **9. Stop** | TCP | `0xFB / 0x01` | `byte21 = 0x00` | Stream beendet |
| **10. Close** | Sockets| - | Sockets.close() | Resourcen frei |
