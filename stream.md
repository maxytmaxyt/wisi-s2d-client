Um einen **MPEG-TS-Videostream** vom WISI OR S2D Dongle anzufordern, musst du eine definierte Abfolge von **TCP-Steuerbefehlen (Port 8802)** und **UDP-Data-Pulls (Port 8800)** durchführen [cite: 85, 86, 87].

Hier ist der genaue, schrittweise Ablauf der Stream-Anfrage [cite: 87]:

---

### 1. TCP-Initialisierung (Port 8802)
Beide Befehle werden als 31-Byte USBC-Pakete an den Steuerkanal (TCP Port 8802) gesendet [cite: 84, 85]:
1. **Handshake (`0xF6 / 0x16`):** Status abfragen, bis der Dongle im ersten Byte der Antwort `0x01` (Bereit) meldet [cite: 85, 87].
2. **Init Phase 2 (`0xF6 / 0x17`):** Zweite Bestätigung für den Sitzungsaufbau senden [cite: 85, 87].

---

### 2. Kanal vorbereiten (TCP Port 8802)
Vor dem eigentlichen Tuning wird der gewünschte Sender vorbereitet [cite: 87]:
1. **Prepare (`0xF6 / 0x03`):** Kanalauswahl im Dongle vorbereiten [cite: 85, 87].
2. **Kanal-Info (`0xF6 / 0x32` & `0xF6 / 0x33`):** XML-Metadaten (`<ch_Info>`) zum Kanal abrufen [cite: 85, 87].
3. **Signal pollen (`0xF6 / 0x02`):** Abfrage der Signalstärke und -qualität [cite: 85, 87].

---

### 3. Kanal aktivieren / Tune (TCP Port 8802)
* **Befehl:** `0xF6 / 0x01` [cite: 85, 87]
* **Payload (USBC Byte 21 & 22):** Enthält den **internen 16-Bit-Kanalindex** des Dongles als Big-Endian-Wert (`(index >> 8) & 0xFF`, `index & 0xFF`) [cite: 19, 42, 85]:
  * *Beispiel:* Kanal-Index `4` (ZDF HD / RTL Austria) \\(\rightarrow\\) `0x00 0x04` [cite: 1, 19, 87].
  * *Beispiel:* Kanal-Index `300` \\(\rightarrow\\) `0x01 0x2C` [cite: 19].

---

### 4. Stream freischalten (TCP Port 8802)
* **Befehl:** `0xF8 / 0x07` [cite: 86, 87]
* Schaltet die Ausgabe des Videostreams auf dem Dongle frei [cite: 86, 87].

---

### 5. UDP-Streaming & Pull-Schleife (Port 8800)
Der Dongle sendet Videodaten nicht von alleine, sondern erfordert kontinuierliche **UDP-Pulls auf Port 8800** [cite: 86, 87]:

1. **UDP-Socket binden:** Der UDP-Socket muss auf Port 8800 gebunden sein, **bevor** die Stream-Freigabe gesendet wird [cite: 21].
2. **Erster DVB-Pull (`0xF9 / 0x01`):**
   * Request mit Opcode `0xF9 / 0x01` [cite: 28, 86].
   * Setze **Byte 21 = `0x00`** (signalisiert den ersten Block) [cite: 28, 87].
3. **Tune-Bestätigung über TCP:** Sende `0xF6 / 0x17` mit Payload `0x01 0x00 0x00 0x00` [cite: 87].
4. **Folge-Pulls (`0xF9 / 0x01` Schleife):**
   * Sende fortlaufend `0xF9 / 0x01` [cite: 28, 87].
   * Setze **Byte 21 = `0x01`** für alle weiteren Blöcke [cite: 28, 87].

---

### Empfangene Datenstruktur (MPEG-TS)
Der Dongle antwortet auf jeden UDP-Pull mit einem Datenblock (typischerweise ca. 32.740 Bytes) [cite: 48, 87]. Darin sind **174 standardisierte MPEG-TS-Pakete à 188 Bytes** enthalten [cite: 48]. Du musst im empfangenen Buffer lediglich nach dem DVB-Synchronisationsbyte `0x47` suchen und den Stream an 188-Byte-Grenzen ausrichten [cite: 48, 87].

---

💡 Möchtest du dazu ein kurzes Python-Beispiel oder eine C++-Funktion für den ESP32-S3 sehen, die genau diesen Ablauf umsetzt?
