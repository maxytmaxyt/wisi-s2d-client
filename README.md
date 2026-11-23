# WISI OR S2D – DVB-over-IP Client

Python-Client und Web-Oberfläche für den **WISI OR S2D** DVB-S2-Satelliten-Dongle (baugleich mit TiViCon OR S2D / Schwaiger DSRD0100). Entstanden durch PCAP-Analyse, dekompilierten APK-Quellcode und Live-Tests gegen die echte Hardware.

> **Protokoll vollständig reverse-engineert** – alle 5 APIX-Befehlsklassen (`0xF6`–`0xFB`) sind dokumentiert und implementiert.

---

## Inhaltsverzeichnis

- [Features](#features)
- [Voraussetzungen & Installation](#voraussetzungen--installation)
- [Schnellstart](#schnellstart)
- [Web-Oberfläche](#web-oberfläche)
- [CLI-Nutzung](#cli-nutzung)
- [24/7-Betrieb](#247-betrieb)
- [Projektstruktur](#projektstruktur)
- [Tests](#tests)
- [Dokumentation](#dokumentation)

---

## Features

- **Live-TV & Radio** direkt im Browser (HTML5-Player via `mpegts.js`)
- **VLC-Streaming** per HTTP und M3U-Playlist-Export
- **Aufnahmen** mit Timer-Scheduler und Timeshift-Puffer
- **EPG** (Programmführer) mit 1-Klick-Aufnahme
- **Sendersuchlauf** (manuell / automatisch / Netzwerk) mit Live-Fortschritt
- **Signalüberwachung** (AGC-Stärke, SNR-Qualität, Tuner-Lock)
- **AES-128-ECB Entschlüsselung** – der Dongle verschlüsselt alle TS-Pakete (auch FTA) auf der Netzwerkstrecke; der Client entschlüsselt automatisch
- **Hardware-Diagnose** (Firmware-Version, MAC, Chip-ID, Seriennummer)
- **PCAP-Analyse** für Protokoll-Debugging

---

## Voraussetzungen & Installation

- Python **3.10+**
- Paket [`cryptography`](https://pypi.org/project/cryptography/) (für AES-128-ECB)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell

pip install -e .
```

Nach der Installation ist der Befehl `wisi` verfügbar. Ohne Installation geht auch `python src/wisi/wisi.py`.

---

## Schnellstart

```bash
# Web-Oberfläche starten (Browser öffnet sich automatisch)
wisi --ui

# Kanalliste anzeigen
wisi --ip 192.168.178.32 --channels

# 60 Sekunden aufnehmen und direkt entschlüsseln
wisi --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output aufnahme.ts --decrypt
```

Die Standard-IP `192.168.178.32` kann mit `--ip` überschrieben werden.

---

## Web-Oberfläche

```bash
wisi --ui
# oder direkt mit IP:
wisi --ui --ip 192.168.178.32
```

Erreichbar unter **http://localhost:8888** – und im gesamten Heimnetz unter `http://<Server-IP>:8888`.

| Bereich | Funktion |
|---------|----------|
| **Live-TV** | HTML5-Player, VLC-Link, M3U-Export |
| **Senderliste** | Suche, Filter (TV / Radio / FTA / Verschlüsselt) |
| **EPG** | Aktuelle und nächste Sendung, 1-Klick-Aufnahme |
| **Aufnahmen** | Starten, stoppen, herunterladen, löschen, im Browser abspielen |
| **Timer** | Sendungen nach Uhrzeit und Dauer programmieren |
| **Tuner** | Transponder einstellen, DVB-S2-Suchlauf |
| **Signal** | Live AGC / SNR / Lock-Anzeige |
| **Diagnose** | Dongle-Info, PCAP-Analyse, Opcode-Tester |

---

## CLI-Nutzung

### Kanalliste

```bash
wisi --channels
```

### Stream aufnehmen

```bash
# Aufnahme mit automatischer Entschlüsselung am Ende:
wisi --stream --pat-idx 4 --duration 60 --output aufnahme.ts --decrypt

# Unbegrenzt aufnehmen (STRG+C zum Beenden):
wisi --stream --pat-idx 4 --output live.ts --decrypt

# Direkt nach stdout (für VLC-Pipe):
wisi --stream --pat-idx 4 --output - | vlc -
```

`--pat-idx` ist der Kanalindex aus `--channels`. `--duration 0` = unbegrenzt.

### Gespeicherte Datei entschlüsseln

```bash
# In-place (überschreibt die Originaldatei):
wisi --decrypt-ts aufnahme.ts

# In neue Datei:
wisi --decrypt-ts aufnahme.ts --output aufnahme_klar.ts
```

### EPG exportieren

```bash
wisi --epg --epg-limit 20 --epg-output epg.json
```

### PCAP analysieren

```bash
wisi --pcap capture.pcap
```

### Alle CLI-Optionen

| Option | Beschreibung |
|--------|-------------|
| `--ui`, `--web` | Web-Oberfläche starten |
| `--ip IP` | IP-Adresse des Dongles (Standard: `192.168.178.32`) |
| `--channels` | Kanalliste anzeigen |
| `--stream` | MPEG-TS-Stream starten |
| `--pat-idx N` | Kanalindex für `--stream` (Standard: `4`) |
| `--output DATEI` | Ausgabedatei oder `-` für stdout |
| `--duration SEK` | Aufnahmedauer in Sekunden (`0` = unbegrenzt) |
| `--decrypt` | Stream nach Aufnahme automatisch entschlüsseln |
| `--decrypt-ts DATEI` | Gespeicherte `.ts`-Datei entschlüsseln |
| `--epg` | EPG als JSON exportieren |
| `--epg-output DATEI` | EPG-Zieldatei (Standard: `epg.json`) |
| `--epg-limit N` | Nur die ersten N Sender abfragen |
| `--pcap DATEI` | PCAP-Datei auf APIX-Befehle analysieren |
| `--discover` | Dongle im Netzwerk suchen |
| `--probe-opcode 0xNN` | Einzelnen Opcode testen |
| `--debug` | Debug-Logs aktivieren |

---

## 24/7-Betrieb

Für Dauerbetrieb (z. B. Raspberry Pi oder Mini-PC) als `systemd`-Dienst einrichten:

```bash
# Raspberry Pi / Linux:
chmod +x scripts/setup_raspberry_pi.sh
./scripts/setup_raspberry_pi.sh
```

Danach läuft der Dienst automatisch beim Hochfahren. Alternativ unter Windows: [`scripts/start_windows_service.bat`](scripts/start_windows_service.bat) ausführen.

**Empfehlung:** Dongle per USB-C Datenkabel direkt an den Server anschließen (zusätzlich zum 12V-Netzteil). Der Server verbindet sich per LAN oder schnellem WLAN mit dem Heimnetz – so entfällt der ältere Wi-Fi-4-Chip des Dongles.

---

## Projektstruktur

```
src/
├── protocol.py        # USBC-Builder und Protokoll-Konstanten
├── connection.py      # TCP-Verbindung, Handshake, send_recv
├── models.py          # Channel, ServiceEntry, Datenmodelle
├── channels.py        # Kanalliste laden & parsen (0xF6/0x20+0x21)
├── scan.py            # DVB-S2 Tuner, LNB, Suchlauf, Dongle-Info
├── prepare.py         # Kanalwechsel und Signal-Check
├── decrypt.py         # AES-128-ECB TS-Entschlüsselung
├── stream.py          # UDP-MPEG-TS-Pull-Schleife
├── keepalive.py       # Keep-Alive-Thread
├── ts_sync.py         # TS-Paket-Synchronisation
├── dongle_info.py     # 3-stufige Hardware-Abfrage (0xFA)
├── sac.py             # CI+/SAC-Handshake (0xFA/0x01–0x03)
├── wisi/              # CLI-Einstiegspunkte
│   ├── wisi.py        # Haupt-CLI
│   ├── client.py      # Stream-Client
│   ├── epg.py         # EPG-Export
│   ├── discovery.py   # Gerätesuche
│   ├── pcap.py        # PCAP-CLI
│   └── probe.py       # Opcode-Tester
├── ui/                # Web-Oberfläche
│   ├── app.py         # Starlette-Anwendung & Routing
│   ├── streamer.py    # DongleManager (zentrale Steuerklasse)
│   ├── stream_engine.py # Live-Streaming & Client-Verteilung
│   ├── scheduler.py   # Aufnahme- & Timer-Verwaltung
│   ├── channels_mgr.py # Kanalliste & EPG-Cache
│   ├── scanner.py     # Transponder-Tuning & Suchlauf
│   ├── playlist.py    # M3U-Generator
│   ├── transcoder.py  # FFmpeg-Echtzeit-Transkodierung
│   └── static/        # HTML/CSS/JS-Frontend
└── tools/
    ├── menu.py        # Interaktives Konsolenmenü
    └── pcap_parser.py # PCAP-Parsing & APIX-Analyse

research/              # Reverse-Engineering-Dokumentation
├── DETAILS.md         # Technische Gesamtreferenz
├── PROTOCOL.md        # APIX-Befehlsreferenz (alle Opcodes)
├── stream.md          # Streaming-Ablauf im Detail
├── pcap_analysis.md   # PCAP-Analyse-Ergebnisse
└── ...                # APK-Analyse-Skripte

tests/                 # Unit-Tests (28 Tests)
scripts/               # Setup-Skripte (Raspberry Pi, Windows)
```

---

## Tests

```bash
python -m pytest tests/ -v
```

---

## Dokumentation

| Datei | Inhalt |
|-------|--------|
| [`research/PROTOCOL.md`](research/PROTOCOL.md) | Vollständige APIX-Befehlsreferenz mit allen Opcodes und Paketstrukturen |
| [`research/DETAILS.md`](research/DETAILS.md) | Technische Gesamtreferenz: Hardware, Protokoll-Architektur, CI+/SAC |
| [`research/stream.md`](research/stream.md) | UDP-Streaming-Ablauf, Timing, Sequenznummern |
| [`research/pcap_analysis.md`](research/pcap_analysis.md) | Ergebnisse der PCAP-Mitschnitt-Analyse |
