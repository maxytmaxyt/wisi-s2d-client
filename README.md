# WISI OR S2D – DVB-over-IP Client

Python-Client für den **WISI OR S2D** (DVB-S2-Satelliten-Dongle, baugleich mit TiViCon OR S2D / Schwaiger DSRD0100). Basiert auf PCAP-Mitschnitten, der dekompilierten TV2Smart-App und Live-Verifikation gegen den echten Dongle.

> Details zu Protokoll, Forschungsstand und Streaming-Ablauf: [research/DETAILS.md](research/DETAILS.md) & [research/stream.md](research/stream.md)

## Protokoll-Entschlüsselungsstatus (100 % aller 5 APIX-Klassen)

Alle fünf im Hersteller-SDK (`com.crenova.tv.dongle.dvb.sdk.messages.*`) vorhandenen APIX-Befehlsklassen sind vollständig reverse-engineert, dokumentiert und im Client hinterlegt:

| APIX-Klasse | Funktionsbereich | Status |
|---|---|---|
| **`0xF6`** | Tuner, DVB-S2 LNB/DiSEqC/Satellit (`0x07..0x09`), Sendersuchlauf (`0x01, 0x02, 0x10..0x12`), Kanalwechsel (`0x03`), Kanalliste (`0x20..0x22`), Bouquets (`0x22..0x2B`), EPG (`0x30..0x38`), Keep-Alive (`0x16/0x17`), Reset (`0x00/0x40`) | **100 % entschlüsselt** (`protocol.py`, `channels.py`, `prepare.py`, `epg.py`, `scan.py`) |
| **`0xF8`** | CAS / Smartcard-MMI (`0x00..0x06`, `0x10..0x17`) & Stream-Stop / Sleep-Mode (`0x07`) | **100 % entschlüsselt** (`protocol.py`, `stream.py`) |
| **`0xF9`** | UDP-MPEG-TS-Streaming (`0x01, 0x02`), Stream-Status (`0x00`), IPTV-Injektion (`0x03, 0x04, 0x08, 0x0B`), Loopback (`0x05, 0x06`), Speedtest (`0x0A`) + AES-128-ECB Link-Crypto | **100 % entschlüsselt** (`stream.py`, `decrypt.py`) |
| **`0xFA`** | 3-stufige Hardware-/Session-Info (`0x00, 0x07, 0x08`), CI+/SAC-Handshake (`0x01..0x03`, Root-Seed `LukeRanDolphCI+1`), Firmware-Flash (`0x04..0x06`), OTA-Update (`0x0A..0x19`) | **100 % entschlüsselt** (`scan.py`, `research/DETAILS.md`) |
| **`0xFB`** | Werks-/Produktionsmodus (`0x01..0x03`) | **100 % entschlüsselt** (`research/DETAILS.md`) |

---

## Voraussetzungen

- Python **3.10 oder neuer**
- Paket [`cryptography`](https://pypi.org/project/cryptography/) (für die AES-128-ECB-Entschlüsselung der vom Dongle link-verschlüsselten MPEG-TS-Pakete)

```bash
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .\.venv\Scripts\Activate.ps1  # Windows PowerShell
pip install -e .
```

Nach der Installation ist der Befehl `wisi` verfügbar. Ohne Installation: `python src/wisi/wisi.py`.

---

## Ausführen

Die Standard-IP in den Beispielen ist `192.168.178.32` – bei Bedarf durch die IP deines Dongles ersetzen.

### 1. Kanalliste anzeigen

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --channels
```

### 2. Stream aufzeichnen & entschlüsseln

Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (auch bei FTA-Sendern) auf der Netzwerkstrecke mit AES-128-ECB. Mit `--decrypt` wird die gespeicherte `.ts`-Datei direkt am Ende der Aufnahme entschlüsselt:

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --stream --pat-idx 4 --duration 60 --output stream.ts --decrypt
```

- `--duration 0` = unbegrenzt (Beenden mit `STRG+C`; auch dann wird bei `--decrypt` am Ende entschlüsselt).
- `--pat-idx 4` wählt den Kanal mit Index `4` aus der Senderliste (`--channels` zeigt alle Indizes).

```bash
vlc stream.ts   # Aufzeichnung in VLC abspielen
```

### 3. Gespeicherte `.ts`-Datei nachträglich entschlüsseln

Falls ein Stream ohne `--decrypt` aufgenommen wurde, kann die Datei jederzeit nachträglich entschlüsselt werden:

```bash
# Eigenständiges Skript (überschreibt stream.ts in-place):
python src/wisi/decrypt.py stream.ts

# Oder in eine neue Zieldatei schreiben:
python src/wisi/decrypt.py stream.ts --output stream_clear.ts

# Alternativ über wisi.py:
python src/wisi/wisi.py --decrypt-ts stream.ts
```

### 4. EPG laden

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --epg --epg-limit 10 --epg-output epg.json
```

### 5. PCAP analysieren

```bash
python src/wisi/wisi.py --pcap "research/assets/PCAPdroid_12_Okt._16_16_04.pcap"
```

### Alle Optionen (`wisi.py`)

| Option | Beschreibung |
|---|---|
| `--ip IP` | IP-Adresse des Dongles (Standard: `192.168.178.32`) |
| `--channels` | Kanalliste vom Gerät laden und ausgeben |
| `--stream` | MPEG-TS-Stream starten |
| `--decrypt` | Bei `--stream`: gespeicherte `.ts`-Datei am Ende automatisch entschlüsseln |
| `--decrypt-ts DATEI` | Gespeicherte `.ts`-Datei nachträglich entschlüsseln |
| `--pat-idx N` | Interner Kanalindex des Dongles für `--stream` (Standard: 4) |
| `--output DATEI` | Ausgabedatei oder `-` für stdout (Standard: `stream.ts`) |
| `--duration SEK` | Streamdauer in Sekunden (0 = unbegrenzt) |
| `--epg` | EPG der Sender als JSON laden |
| `--epg-output DATEI` | EPG-Ausgabedatei (Standard: `epg.json`) |
| `--epg-limit N`, `--limit N` | EPG nur für die ersten N Sender laden |
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

```text
src/
├── protocol.py        # USBC-Builder, Protokoll-Konstanten und Befehlspakete
├── scan.py            # DVB-S2 LNB/DiSEqC/Satellit/Suchlauf (0xF6/0x01..0x12) & Dongle-Info/SAC (0xFA)
├── connection.py      # TCP-Transporthelfer (send_recv) und Handshake (connect/disconnect)
├── models.py          # Channel, ServiceEntry, FALLBACK_SERVICE (0x40=TV, 0x48=Radio)
├── channels.py        # Kanalliste laden & XML parsen (0xF6/0x20+0x21+0x22)
├── keepalive.py       # Keep-Alive-Thread (0xF6/0x16-Ping)
├── prepare.py         # Kanalwechsel (0xF6/0x03), Kanal-Info (0x32/0x33) & Signal-Check (0x02)
├── decrypt.py         # AES-128-ECB MPEG-TS-Entschlüsselung (Block & Datei)
├── stream.py          # UDP-MPEG-TS-Pull-Schleife (0xF9/0x01) + Stream-Teardown (0xF8/0x07)
├── wisi/              # CLI-Einstiegspunkte und Subkommandos
│   ├── wisi.py        # Haupt-CLI (Einstieg)
│   ├── client.py      # Stream-Client + Re-Exporte
│   ├── channels.py    # Kanalliste ausgeben (--channels)
│   ├── decrypt.py     # Gespeicherte .ts-Dateien entschlüsseln (--decrypt-ts)
│   ├── common.py      # load_services()-Helfer
│   ├── discovery.py   # Experimentelle Gerätesuche (--discover)
│   ├── epg.py         # EPG-Export (--epg)
│   ├── menu.py        # Kompatibilitäts-Wrapper für das Konsolenmenü
│   ├── pcap.py        # PCAP-CLI (--pcap)
│   └── probe.py       # Opcode-Tester (--probe-opcode)
└── tools/             # Hilfswerkzeuge
    ├── menu.py        # Interaktives Konsolenmenü
    └── pcap_parser.py # PCAP-Parsing und APIX-Analyse
research/              # Technische Dokumentation, Mitschnitte und APK-Analysen
tests/                 # Unit-Tests
```
