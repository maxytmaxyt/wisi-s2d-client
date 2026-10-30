# src/ – Quellcode

## Struktur

```
src/
├── protocol.py        # USBC-Builder, Konstanten, TCP-Helfer, connect/disconnect
├── models.py          # Datenmodelle: Channel, ServiceEntry, FALLBACK_SERVICE
├── channels.py        # Kanalliste laden (0xF6/0x20+0x21), XML-Parser
├── keepalive.py       # Keep-Alive-Thread (0x16-Ping alle ~5 s)
├── stream.py          # prepare_channel() + MPEG-TS-Streaming-Schleife
├── wisi/              # CLI-Einstiegspunkte und Subkommandos
└── tools/             # Interne Hilfswerkzeuge
```

## Flat-Module (`src/*.py`)

Diese Module bilden den Kern und werden von `wisi/` und `tools/` importiert:

| Modul | Verantwortlichkeit |
|---|---|
| `protocol.py` | USBC-Frame-Builder, Protokollkonstanten, TCP `connect()`/`disconnect()` |
| `models.py` | `Channel`, `ServiceEntry`, `FALLBACK_SERVICE`, `channel_to_service()` |
| `channels.py` | `fetch_channel_list()`, `channels_to_services()`, XML-Parsing |
| `keepalive.py` | `_keepalive_worker()` – hält TCP-Verbindung mit `0xF6/0x16`-Pings offen |
| `stream.py` | `prepare_channel()`, `stream()` – Tune-Ablauf und UDP-MPEG-TS-Schleife |

## Sub-Pakete

- **[`wisi/`](wisi/)** – CLI-Subkommandos (`--channels`, `--stream`, `--epg` usw.)
- **[`tools/`](tools/)** – Hilfswerkzeuge (`menu.py`, `pcap_parser.py`)
