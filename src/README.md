# src/ – Quellcode

## Struktur

```text
src/
├── protocol.py        # USBC-Builder, Konstanten und APIX-Befehlspakete
├── connection.py      # TCP-Transport (recv_exactly, send_recv) & Session (connect/disconnect)
├── models.py          # Datenmodelle: Channel, ServiceEntry, FALLBACK_SERVICE
├── channels.py        # Kanalliste laden (0xF6/0x20+0x21+0x22), XML-Parser
├── keepalive.py       # Keep-Alive-Thread (0xF6/0x16-Ping)
├── prepare.py         # Kanalwechsel (0xF6/0x03), ch_Info (0x32/0x33) & Signal-Poll (0x02)
├── decrypt.py         # AES-128-ECB MPEG-TS-Link-Entschlüsselung (Block & Datei)
├── stream.py          # UDP-MPEG-TS-Streaming-Schleife (0xF9/0x01) + Teardown (0xF8/0x07)
├── scan.py            # DVB-S2 LNB/DiSEqC/Satellit/Transponder/Suchlauf (0xF6) & Dongle-Info/SAC (0xFA)
├── dongle_info.py     # 3-stufige Hardware-Abfrage (0xFA/0x00, 0x07, 0x08)
├── sac.py             # CI+/SAC-Handshake (0xFA/0x01–0x03, Diffie-Hellman)
├── ts_sync.py         # TS-Paket-Synchronisation / Alignment
├── wisi/              # CLI-Einstiegspunkte und Subkommandos
├── ui/                # Web-Oberfläche (Starlette) und DongleManager
└── tools/             # Interne Hilfswerkzeuge
```

## Kern-Module (`src/*.py`)

Diese Module bilden die Protokoll- und Streaming-Schicht und werden von `wisi/`, `ui/` und `tools/` importiert:

| Modul | Verantwortlichkeit |
|---|---|
| `protocol.py` | 31-Byte USBC-Frame-Builder, Protokollkonstanten, TCP/UDP-Befehlspakete (inkl. Re-Export von `scan.py`) |
| `scan.py` | DVB-S2 LNB (`0xF6/0x07`), DiSEqC (`0x08`), Satellit (`0x09`), Transponder (`0x01`), Suchlauf (`0x10..0x12`), 17-Byte Status-Parser (`0x02`) sowie Dongle-Info & CI+/SAC-Framing (`0xFA/0x00..0x08`) |
| `connection.py` | `recv_exactly()`, `send_recv()`, `connect()`, `disconnect()` (TCP Port 8802) |
| `models.py` | `Channel`, `ServiceEntry`, `FALLBACK_SERVICE`, `channel_to_service()` (`0x40xxxxxx`=TV, `0x48xxxxxx`=Radio, `fta`=Verschlüsselung) |
| `channels.py` | `fetch_channel_list()`, `channels_to_services()`, `<ch_List>`-XML-Parsing |
| `keepalive.py` | `_keepalive_worker()` – hält die TCP-Verbindung mit `0xF6/0x16`-Pings offen |
| `prepare.py` | `prepare_channel()` – schaltet per `0xF6/0x03` (`prog_idx`) um und prüft das Signal (`0xF6/0x02`) |
| `decrypt.py` | `descramble_ts_block()`, `decrypt_ts_file()` – entschlüsselt die AES-128-ECB-Link-Verschlüsselung des Dongles |
| `stream.py` | `stream()` – UDP-Pull-Schleife (`0xF9/0x01`), Sequenzprüfung (`EXTRACSW[12]`), Stream-Stop (`0xF8/0x07`), `DEFAULT_TS_KEY` |
| `dongle_info.py` | `fetch_dongle_info()` – 3-stufige Hardware-Abfrage (`0xFA/0x00` → `0x07` → `0x08`), `DongleInfo` |
| `sac.py` | CI+/SAC-Handshake (`cmd_sac_write`, `cmd_sac_poll_len`, `cmd_sac_read`, `sac_write_and_read_response`), Root-Seed `LukeRanDolphCI+1` |
| `ts_sync.py` | `align_ts_packets()` – TS-Paket-Ausrichtung/Synchronisation |

## Sub-Pakete

- **[`wisi/`](wisi/)** – CLI-Subkommandos (`--channels`, `--stream`, `--decrypt-ts`, `--epg`, `--ui`, …)
- **[`ui/`](ui/)** – Web-Oberfläche (Starlette) mit `DongleManager`, REST-API, Streaming-Engine, Scheduler, Transcoder
- **[`tools/`](tools/)** – Hilfswerkzeuge (`menu.py`, `pcap_parser.py`)

## Web-Oberfläche (`src/ui/`)

| Datei | Verantwortlichkeit |
|---|---|
| `app.py` | Starlette-Anwendung, Routing, Middleware |
| `state.py` | Gemeinsame `manager`-Instanz, `STATIC_DIR`, `INDEX_HTML_PATH` |
| `streamer.py` | `DongleManager` – zentrale Steuerklasse (Verbindung, Kanäle, EPG, Tuner, Signal) |
| `stream_engine.py` | `StreamEngine` – UDP-Empfang, Client-Verteilung, Timeshift-Puffer |
| `scheduler.py` | `RecordingScheduler`, `TimerEntry` – Aufnahmen & Timer |
| `channels_mgr.py` | `ChannelManager` – Kanalliste & EPG-Cache (`epg.json`) |
| `scanner.py` | `TunerScanner` – Transponder-Tuning & Sendersuchlauf |
| `playlist.py` | `generate_m3u_playlist()` – M3U-Generator |
| `transcoder.py` | `find_ffmpeg()`, `transcoded_stream_generator()` – FFmpeg-Transkodierung |
| `api_stream.py` | REST-Endpunkte: Status, Verbindung, Discovery, Info, Kanäle, EPG, Stream, Probe, PCAP |
| `api_record.py` | REST-Endpunkte: Aufnahmen, Timer, Tuner, Suchlauf, Konvertierung, Entschlüsselung |
| `static/` | HTML/CSS/JS-Frontend (index.html, app.js, player.js, tuner.js, timers.js, …) |

## Import-Konvention

Die Module in `src/` sind flach importierbar, sobald `src/` im `sys.path` liegt (siehe `start_ui.py` und die Bootstrap-Blöcke in `wisi/*.py`):

```python
import protocol
from models import Channel, ServiceEntry
from ui.streamer import DongleManager
```

Installiert via `pip install -e .` (siehe `pyproject.toml`: `package-dir = {"" = "src"}`).
