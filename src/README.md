# src/ – Quellcode

## Struktur

```text
src/
├── protocol.py        # USBC-Builder, Konstanten und APIX-Befehlspakete
├── scan.py            # DVB-S2 LNB/DiSEqC/Satellit/Suchlauf (0xF6) & Dongle-Info/SAC-Framing (0xFA)
├── connection.py      # TCP-Transport (recv_exactly, send_recv) & Session (connect/disconnect)
├── models.py          # Datenmodelle: Channel, ServiceEntry, FALLBACK_SERVICE
├── channels.py        # Kanalliste laden (0xF6/0x20+0x21+0x22), XML-Parser
├── keepalive.py       # Keep-Alive-Thread (0xF6/0x16-Ping)
├── prepare.py         # Kanalwechsel (0xF6/0x03), ch_Info (0x32/0x33) & Signal-Poll (0x02)
├── decrypt.py         # AES-128-ECB MPEG-TS-Link-Entschlüsselung (Block & Datei)
├── stream.py          # UDP-MPEG-TS-Streaming-Schleife (0xF9/0x01) + Teardown (0xF8/0x07)
├── wisi/              # CLI-Einstiegspunkte und Subkommandos
└── tools/             # Interne Hilfswerkzeuge
```

## Kern-Module (`src/*.py`)

Diese Module bilden die Protokoll- und Streaming-Schicht und werden von `wisi/` und `tools/` importiert:

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
| `stream.py` | `stream()` – UDP-Pull-Schleife (`0xF9/0x01`), Sequenzprüfung (`EXTRACSW[12]`), Stream-Stop (`0xF8/0x07`) |

## Sub-Pakete

- **[`wisi/`](wisi/)** – CLI-Subkommandos (`--channels`, `--stream`, `--decrypt-ts`, `--epg` usw.)
- **[`tools/`](tools/)** – Hilfswerkzeuge (`menu.py`, `pcap_parser.py`)
