# tests/ – Tests

## Ausführen

```bash
python -m unittest discover -s tests -v
```

## Dateien

| Datei | Beschreibung |
|---|---|
| `test_wisi_tools.py` | Unit-Tests für Discovery, Protokoll-Frames, PCAP-Analyse und Service-Datenbank |

## Testklassen

| Klasse | Was wird getestet |
|---|---|
| `DiscoveryTests` | UDP-Discovery-Request-Builder und Response-Parser |
| `ProtocolFrameTests` | USBC-Frame-Aufbau (`_cmd_16`) und `_send_recv`-USBS-Trailer-Handling |
| `PcapTests` | PCAP-Analyse: `0xF9/0x0A`-Zählung, Legacy-Reject |
| `ServiceDatabaseTests` | `load_services()`-Ablauf (TCP→Keepalive→Kanalliste→Close), `fetch_service_db`-Deaktivierung |
