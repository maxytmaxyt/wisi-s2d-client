# src/wisi_s2d/cli/ – CLI-Einstiegspunkte

Dieses Paket enthält alle CLI-Subkommandos. Haupteinstieg ist `main.py`.

## Dateien

| Datei | Beschreibung |
|---|---|
| `main.py` | Haupt-CLI – verarbeitet Argumente und delegiert an die Submodule |
| `client.py` | Stream-Client (`--stream`, `--decrypt`), Re-Exporte für Rückwärtskompatibilität |
| `ui.py` | Starter für die Web-Oberfläche (`wisi --ui`, `wisi-ui`) |
| `channels.py` | Kanalliste abrufen und tabellarisch ausgeben (`--channels`) |
| `decrypt.py` | Gespeicherte `.ts`-Streamdateien entschlüsseln (`--decrypt-ts` oder direkt als Skript) |
| `common.py` | `load_services()`-Helfer – lädt die Senderliste für andere Submodule |
| `discovery.py` | Experimentelle UDP-Gerätesuche (`--discover`) |
| `epg.py` | EPG-Daten (`0xF6/0x30+0x31`) als JSON exportieren (`--epg`) |
| `menu.py` | Schlanker Kompatibilitäts-Wrapper auf `tools.menu` und `client` |
| `pcap.py` | PCAP-Datei analysieren (`--pcap`) |
| `probe.py` | Einzelnen unbekannten Opcode testen (`--probe-opcode`) |

## Ausführen

```bash
# Gesamtübersicht:
python src/wisi_s2d/cli/main.py --help

# Web-Oberfläche:
python src/wisi_s2d/cli/main.py --ui
# oder:
python src/wisi_s2d/cli/ui.py

# Eigenständiges Entschlüsselungs-Skript:
python src/wisi_s2d/cli/decrypt.py stream.ts
```

## Einstiegspunkte (pyproject.toml)

```toml
[project.scripts]
wisi = "wisi_s2d.cli.main:main"
wisi-ui = "wisi_s2d.cli.ui:main"
```
