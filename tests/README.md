# tests/ – Tests

## Ausführen

```bash
python -m unittest discover -s tests -v
```

## Dateien

| Datei | Beschreibung |
|---|---|
| `test_wisi_tools.py` | Unit-Tests für Discovery, APIX-Protokoll-Frames, EPG-XML-Parsing, AES-128-ECB-TS-Entschlüsselung, PCAP-Analyse und Service-Datenbank |

## Testklassen

| Klasse | Was wird getestet |
|---|---|
| `DiscoveryTests` | UDP-Discovery-Request-Builder und Response-Parser |
| `ProtocolFrameTests` | USBC-Frame-Aufbau (`_cmd_16`), `prog_idx`-Offsets (`0xF6/0x03`, `0x30`, `0x31`, `0x35`, `0xF8/0x07`, `0xF6/0x22`, `0xF9/0x01`), DVB-S2 LNB/DiSEqC/Satellit/Transponder/Suchlauf-Builder (`0xF6/0x07..0x12`), 17-Byte `0xF6/0x02`-Status-Parser, Dongle-Info & CI+/SAC-Framing (`0xFA/0x00..0x08`), `0x48xxxxxx` Radio- vs. Pay-TV-Klassifikation, USBS-Trailer-Handling, 2-Byte-Header-Strip beim EPG-XML und AES-128-ECB-TS-Entschlüsselung (`descramble_ts_block` & `decrypt_ts_file`) |
| `PcapTests` | PCAP-Analyse: `0xF9/0x0A`-Zählung und Ablehnung des Legacy-Service-DB-Decoders |
| `ServiceDatabaseTests` | `load_services()`-Ablauf (TCP → Keepalive → Kanalliste → Close) und `fetch_service_db`-Deaktivierung |
