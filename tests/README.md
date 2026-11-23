# tests/ – Tests

## Ausführen

```bash
python -m unittest discover -s tests -v
# oder mit pytest:
python -m pytest tests/ -v
```

## Dateien

| Datei | Inhalt |
|---|---|
| `test_wisi_tools.py` | `ProtocolFrameTests` – Unit-Tests für Discovery-Request-Builder, APIX-Protokoll-Frames, EPG-XML-Parsing, AES-128-ECB-TS-Entschlüsselung, DVB-S2/SAC-Builder |
| `test_discovery_and_pcap.py` | `DiscoveryTests`, `PcapTests`, `ServiceDatabaseTests` – UDP-Discovery, PCAP-Analyse (`0xF9/0x0A`-Zählung, Legacy-Service-DB-Ablehnung), `load_services()`-Ablauf |
| `test_ui_and_fixes.py` | `ChannelParsingFixTests`, `DongleInfoParserTests`, `DongleManagerTests`, `WebAppStructureTests` – Kanal-Parsing, Dongle-Info-Parser, Manager-Initialisierung/Aufnahmen/Timer/M3U, Web-App-Routen & HTML |

## Testklassen

| Klasse | Datei | Was wird getestet |
|---|---|---|
| `ProtocolFrameTests` | `test_wisi_tools.py` | USBC-Frame-Aufbau (`_cmd_16`), `prog_idx`-Offsets (`0xF6/0x03`, `0x30`, `0x31`, `0x35`, `0xF8/0x07`, `0xF6/0x22`, `0xF9/0x01`), DVB-S2 LNB/DiSEqC/Satellit/Transponder/Suchlauf-Builder (`0xF6/0x07..0x12`), 17-Byte `0xF6/0x02`-Status-Parser, Dongle-Info & CI+/SAC-Framing (`0xFA/0x00..0x08`), `0x48xxxxxx` Radio- vs. Pay-TV-Klassifikation, USBS-Trailer-Handling, 2-Byte-Header-Strip beim EPG-XML und AES-128-ECB-TS-Entschlüsselung (`descramble_ts_block` & `decrypt_ts_file`) |
| `DiscoveryTests` | `test_discovery_and_pcap.py` | UDP-Discovery-Request-Builder und Response-Parser |
| `PcapTests` | `test_discovery_and_pcap.py` | PCAP-Analyse: `0xF9/0x0A`-Zählung und Ablehnung des Legacy-Service-DB-Decoders |
| `ServiceDatabaseTests` | `test_discovery_and_pcap.py` | `load_services()`-Ablauf (TCP → Keepalive → Kanalliste → Close) und `fetch_service_db`-Deaktivierung |
| `ChannelParsingFixTests` | `test_ui_and_fixes.py` | Kanal-Parsing (Dezimal/Hex `prog_idx`), HTML-Entities, `channel_to_service` |
| `DongleInfoParserTests` | `test_ui_and_fixes.py` | 3-stufiger Dongle-Info-Parser (`0xFA/0x00`, `0x07`, `0x08`) |
| `DongleManagerTests` | `test_ui_and_fixes.py` | Manager-Initialisierung, Cached-EPG, Aufnahmen, Timer-CRUD, M3U-Generierung, Stream-Engine Subscribe/Unsubscribe |
| `WebAppStructureTests` | `test_ui_and_fixes.py` | Registrierte Routen und HTML-Komponenten der Web-App |

## Hinweise

- Die Tests fügen `src/` über `sys.path.insert(0, ...)` in den Suchpfad ein.
- Beim Ausführen werden u. a. `recordings/timers.json` und temporäre Dateien angelegt; diese werden automatisch bereinigt bzw. sind harmlos.
- Gesamt: **28 Tests** (Stand: aktueller Repository-Stand).
