# WISI OR S2D – DVB-over-IP Client

Python-Client und Web Control Center für den **WISI OR S2D** DVB-S2-Satelliten-Dongle (baugleich mit TiViCon OR S2D / Schwaiger DSRD0100). Entstanden durch PCAP-Analyse, dekompilierten APK-Quellcode und Live-Tests gegen die echte Hardware.

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

- **Live-TV & Radio** direkt im Browser (HTML5-Player via `mpegts.js`, optional H.264/AAC-Transkodierung per FFmpeg)
- **Multi-Client-Streaming** – beliebig viele Browser-/VLC-Clients gleichzeitig auf einen Dongle-Stream
- **VLC-Streaming** per HTTP und M3U-Playlist-Export (TVG-Tags)
- **Aufnahmen** mit Timer-Scheduler, Timeshift-Puffer (Pause/Rewind/Scrub) und `.ts`→`.mp4`-Konvertierung
- **EPG** (Programmführer) mit 1-Klick-Aufnahme
- **Sendersuchlauf** (manuell / automatisch / Netzwerk) mit Live-Fortschritt
- **Signalüberwachung** (AGC-Stärke, SNR-Qualität, Tuner-Lock)
- **AES-128-ECB Entschlüsselung** – der Dongle verschlüsselt alle TS-Pakete (auch FTA) auf der Netzwerkstrecke; der Client entschlüsselt automatisch (Live + Datei)
- **Hardware-Diagnose** (Firmware-Version, MAC, Chip-ID, Seriennummer)
- **PCAP-Analyse** für Protokoll-Debugging

---

## Voraussetzungen & Installation

- Python **3.10+**
- Pakete `cryptography` (AES-128-ECB), `starlette`, `uvicorn` (Web-UI)
- Optional: `ffmpeg` für Browser-Transkodierung und `.ts`→`.mp4`-Konvertierung (wird bei Bedarf automatisch aus `ffmpeg-exe.zip` entpackt oder über `PATH` gefunden)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell

pip install -e .
```

Nach der Installation sind die Befehle `wisi` und `wisi-ui` verfügbar. Ohne Installation geht auch `python start_ui.py` bzw. `python src/wisi/wisi.py`.

---

## Schnellstart

```bash
# Web-Oberfläche starten (Browser öffnet sich automatisch)
wisi --ui
# oder:
python start_ui.py

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
# oder ohne automatischen Browser-Start:
wisi --ui --no-browser
```

Erreichbar unter **http://localhost:8888** – und im gesamten Heimnetz unter `http://<Server-IP>:8888`.

| Bereich | Funktion |
|---------|----------|
| **Live-TV** | HTML5-Player (mpegts.js), VLC-Link, M3U-Export, optional FFmpeg-Transkodierung |
| **Senderliste** | Suche, Filter (TV / Radio / FTA / Verschlüsselt), EPG-Anzeige |
| **EPG** | Aktuelle und nächste Sendung, 1-Klick-Aufnahme |
| **Aufnahmen** | Starten, stoppen, herunterladen, löschen, im Browser abspielen (fMP4/AAC), `.ts`→`.mp4` |
| **Timer** | Sendungen nach Uhrzeit und Dauer programmieren |
| **Timeshift** | Live-Puffer (Pause/Rewind/Scrub), als Aufnahme sichern |
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

### Aktuelle Struktur

```text
src/
├── protocol.py        # USBC-Builder und Protokoll-Konstanten
├── connection.py      # TCP-Verbindung, Handshake, send_recv
├── models.py          # Channel, ServiceEntry, Datenmodelle
├── channels.py        # Kanalliste laden & parsen (0xF6/0x20+0x21+0x22)
├── scan.py            # DVB-S2 Tuner, LNB, Suchlauf, Dongle-Info/SAC-Framing
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
│   ├── ui.py          # Web-UI-Starter
│   ├── epg.py         # EPG-Export
│   ├── discovery.py   # Gerätesuche
│   ├── pcap.py        # PCAP-CLI
│   ├── probe.py       # Opcode-Tester
│   ├── channels.py    # Kanalliste CLI
│   ├── decrypt.py     # Entschlüsselungs-CLI
│   ├── common.py      # load_services()-Helfer
│   └── menu.py        # Kompatibilitäts-Wrapper
├── ui/                # Web-Oberfläche (Starlette)
│   ├── app.py         # Routing & Anwendung
│   ├── state.py       # Gemeinsame Manager-Instanz
│   ├── streamer.py    # DongleManager (zentrale Steuerklasse)
│   ├── stream_engine.py # Live-Streaming & Client-Verteilung
│   ├── scheduler.py   # Aufnahme- & Timer-Verwaltung
│   ├── channels_mgr.py # Kanalliste & EPG-Cache
│   ├── scanner.py     # Transponder-Tuning & Suchlauf
│   ├── playlist.py    # M3U-Generator
│   ├── transcoder.py  # FFmpeg-Echtzeit-Transkodierung
│   ├── api_stream.py  # REST: Status, Sender, EPG, Stream, Diagnose
│   ├── api_record.py  # REST: Aufnahmen, Timer, Tuner
│   └── static/        # HTML/CSS/JS-Frontend (index.html, app.js, …)
└── tools/
    ├── menu.py        # Interaktives Konsolenmenü
    └── pcap_parser.py # PCAP-Parsing & APIX-Analyse

research/              # Reverse-Engineering-Dokumentation
├── DETAILS.md         # Technische Gesamtreferenz
├── PROTOCOL.md        # APIX-Befehlsreferenz (alle Opcodes)
├── stream.md          # Streaming-Ablauf im Detail
├── pcap_analysis.md   # PCAP-Analyse-Ergebnisse
├── apk_reverse_engineering.md
├── firmware_and_cloud_architecture.md
├── firmware_extraction_methods.md
└── ...                # APK-Analyse-Skripte

tests/                 # Unit-Tests (28 Tests, 3 Dateien)
scripts/               # Setup-Skripte (Raspberry Pi, Windows)
recordings/            # Laufzeit: Aufnahmen & Timer (wird angelegt)
```

### Vorgeschlagene neue Ordnerstruktur (Entwurf, noch nicht umgesetzt)

Die aktuelle Struktur ist historisch gewachsen: flache Module in `src/`, drei parallele Pakete (`wisi/`, `ui/`, `tools/`) und ein sehr großer `research/`-Ordner mit 100+ Analyse-Skripten. Vorschlag für eine klarere, paketorientierte Struktur:

```text
wisi-s2d-client/
├── pyproject.toml
├── README.md
├── start_ui.py / start_ui.bat
├── src/
│   └── wisi_s2d/                 # einziges Top-Level-Paket
│       ├── __init__.py
│       ├── protocol/              # Protokollschicht
│       │   ├── framing.py        # USBC-Builder (protocol.py)
│       │   ├── commands.py       # cmd_*-Builder
│       │   ├── connection.py     # TCP-Transport
│       │   ├── keepalive.py
│       │   └── constants.py
│       ├── core/                  # Domänenlogik
│       │   ├── models.py
│       │   ├── channels.py
│       │   ├── scan.py
│       │   ├── prepare.py
│       │   ├── stream.py
│       │   ├── decrypt.py
│       │   ├── ts_sync.py
│       │   ├── dongle_info.py
│       │   └── sac.py
│       ├── cli/                   # ehem. wisi/
│       │   ├── main.py           # wisi.py
│       │   ├── client.py
│       │   ├── ui.py
│       │   ├── epg.py
│       │   ├── channels.py
│       │   ├── decrypt.py
│       │   ├── discovery.py
│       │   ├── pcap.py
│       │   ├── probe.py
│       │   ├── common.py
│       │   └── menu.py
│       ├── web/                   # ehem. ui/
│       │   ├── app.py
│       │   ├── state.py
│       │   ├── streamer.py
│       │   ├── stream_engine.py
│       │   ├── scheduler.py
│       │   ├── channels_mgr.py
│       │   ├── scanner.py
│       │   ├── playlist.py
│       │   ├── transcoder.py
│       │   ├── api_stream.py
│       │   ├── api_record.py
│       │   └── static/
│       └── tools/                 # ehem. tools/
│           ├── menu.py
│           └── pcap_parser.py
├── tests/
│   ├── test_protocol.py
│   ├── test_discovery_pcap.py
│   └── test_ui.py
├── research/
│   ├── docs/                      # Markdown-Dokumentation
│   ├── scripts/                   # Analyse-Skripte (*.py)
│   ├── assets/                    # Binärartefakte
│   └── archive/                   # Legacy
└── scripts/                       # Setup/Deployment
```

Vorteile: ein einziges importierbares Paket (`wisi_s2d`), klare Schichtentrennung (Protokoll / Domäne / CLI / Web), Analyse-Skripte aus dem Paketpfad herausgeholt (keine Import-Kollisionen), Tests spiegeln Paketstruktur wider. Migration wäre rein mechanisch (Imports anpassen, `pyproject.toml` aktualisieren).

---

## Tests

```bash
python -m unittest discover -s tests -v
# oder mit pytest:
python -m pytest tests/ -v
```

Testdateien:

| Datei | Inhalt |
|---|---|
| `tests/test_wisi_tools.py` | `ProtocolFrameTests` – USBC-Frames, Prog-Idx-Offsets, EPG-XML, AES-Entschlüsselung, DVB-S2/SAC-Builder |
| `tests/test_discovery_and_pcap.py` | `DiscoveryTests`, `PcapTests`, `ServiceDatabaseTests` |
| `tests/test_ui_and_fixes.py` | `ChannelParsingFixTests`, `DongleInfoParserTests`, `DongleManagerTests`, `WebAppStructureTests` |

Insgesamt **28 Tests**.

---

## Dokumentation

| Datei | Inhalt |
|-------|--------|
| [`research/PROTOCOL.md`](research/PROTOCOL.md) | Vollständige APIX-Befehlsreferenz mit allen Opcodes und Paketstrukturen |
| [`research/DETAILS.md`](research/DETAILS.md) | Technische Gesamtreferenz: Hardware, Protokoll-Architektur, CI+/SAC |
| [`research/stream.md`](research/stream.md) | UDP-Streaming-Ablauf, Timing, Sequenznummern |
| [`research/pcap_analysis.md`](research/pcap_analysis.md) | Ergebnisse der PCAP-Mitschnitt-Analyse |
| [`research/AGENTS.md`](research/AGENTS.md) | Hinweise und Checkliste für KI-Agenten |
