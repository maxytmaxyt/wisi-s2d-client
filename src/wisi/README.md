# src/wisi/ – CLI-Einstiegspunkte

Dieses Paket enthält alle CLI-Subkommandos. Haupteinstieg ist `wisi.py`.

## Dateien

| Datei | Beschreibung |
|---|---|
| `wisi.py` | Haupt-CLI – verarbeitet Argumente und delegiert an die Submodule |
| `client.py` | Stream-Client (`--stream`, `--decrypt`), Re-Exporte für Rückwärtskompatibilität |
| `channels.py` | Kanalliste abrufen und tabellarisch ausgeben (`--channels`) |
| `decrypt.py` | Gespeicherte `.ts`-Streamdateien entschlüsseln (`--decrypt-ts` oder direkt als Skript) |
| `common.py` | `load_services()`-Helfer – lädt die Senderliste für andere Submodule |
| `discovery.py` | Experimentelle UDP-Gerätesuche (`--discover`) |
| `epg.py` | EPG-Daten (`0xF6/0x30+0x31`) als JSON exportieren (`--epg`) |
| `menu.py` | Schlanker Kompatibilitäts-Wrapper auf `tools.menu` und `wisi.client` |
| `pcap.py` | PCAP-Datei analysieren (`--pcap`) |
| `probe.py` | Einzelnen unbekannten Opcode testen (`--probe-opcode`) |

## Ausführen

```bash
# Gesamtübersicht:
python src/wisi/wisi.py --help

# Eigenständiges Entschlüsselungs-Skript:
python src/wisi/decrypt.py stream.ts
```
