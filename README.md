# WISI OR S2D – DVB-over-IP Client

Python-Client für den **WISI OR S2D** (DVB-S2-Satelliten-Dongle). Basiert auf eigenen PCAP-Mitschnitten und der Analyse der TV2Smart-App.

> Details zu Protokoll, Forschungsstand und offenen Punkten: [research/DETAILS.md](research/DETAILS.md)

---

## Voraussetzungen

- Python **3.10 oder neuer**
- Keine zusätzlichen Laufzeitpakete erforderlich

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -e .
```

Nach der Installation ist der Befehl `wisi` verfügbar. Ohne Installation: `python src/wisi/wisi.py`.

---

## Ausführen

Die Standard-IP in den Beispielen ist `192.168.178.32` – durch die IP deines Dongles ersetzen.

### Kanalliste anzeigen

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --channels
```

### Stream aufzeichnen

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output stream.ts
```

`--duration 0` = unbegrenzt. `--pat-idx 4` stammt aus dem Beispielmitschnitt (interner Dongle-Kanalindex 4, Programm 4914) – vorher die Kanalliste prüfen.

```bash
vlc stream.ts   # Aufzeichnung abspielen
```

Direkt an VLC pipen (erst nach erfolgreichem lokalem Test):

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --output - | vlc -
```

### EPG laden

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --epg --epg-output epg.json
```

### PCAP analysieren

```bash
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_16_04.pcap"
```

### Alle Optionen

| Option | Beschreibung |
|---|---|
| `--ip IP` | IP-Adresse des Dongles (Standard: `192.168.178.32`) |
| `--channels` | Kanalliste vom Gerät laden und ausgeben |
| `--stream` | MPEG-TS-Stream starten |
| `--pat-idx N` | Interner 16-Bit-Kanalindex des Dongles für `--stream` (Standard: 4) |
| `--output DATEI` | Ausgabedatei oder `-` für stdout |
| `--duration SEK` | Streamdauer in Sekunden (0 = unbegrenzt) |
| `--epg` | EPG aller Sender als JSON laden |
| `--epg-output DATEI` | EPG-Ausgabedatei (Standard: `epg.json`) |
| `--epg-limit N` | EPG nur für die ersten N Sender laden |
| `--pcap DATEI` | PCAP-Datei auf APIX-Befehle analysieren |
| `--pcap-extract DATEI` | Größte `0xF9/0x0A`-Speedtest-Geräteantwort aus PCAP extrahieren |
| `--decode-service-db DATEI` | Veraltete Option; wird abgelehnt, da `F9/0A` ein Speedtest ist |
| `--discover` | Experimentelle UDP-Gerätesuche |
| `--probe-opcode 0xNN` | Einzelnen unbekannten Opcode testen |
| `--debug` | Debug-Logs aktivieren |

---

## Tests

```bash
python -m unittest discover -s tests -v
```

---

## Projektstruktur

```
src/
├── protocol.py        # USBC-Builder, Konstanten, TCP-Helfer
├── models.py          # Channel, ServiceEntry, FALLBACK_SERVICE
├── channels.py        # Kanalliste laden (0xF6/0x20+0x21)
├── keepalive.py       # Keep-Alive-Thread (0x16-Ping)
├── stream.py          # prepare_channel + MPEG-TS-Stream
├── wisi/              # CLI-Einstiegspunkte und Subkommandos
│   ├── wisi.py        # Haupt-CLI (Einstieg)
│   ├── client.py      # Stream-Client + Re-Exporte
│   ├── channels.py    # Kanalliste ausgeben
│   ├── common.py      # load_services()-Helfer
│   ├── discovery.py   # Experimentelle Gerätesuche
│   ├── epg.py         # EPG-Export
│   ├── menu.py        # Interaktives Konsolenmenü
│   ├── pcap.py        # PCAP-CLI
│   └── probe.py       # Opcode-Tester
└── tools/             # Hilfswerkzeuge
    ├── menu.py        # Konsolenmenü-Logik
    └── pcap_parser.py # PCAP-Parsing und APIX-Analyse
research/              # Dokumentation, Mitschnitte, Analysen, APK
tests/
```

Weitere Infos zum Protokoll, Forschungsstand und offenen Punkten: **[research/DETAILS.md](research/DETAILS.md)**
