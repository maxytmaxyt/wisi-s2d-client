# src/wisi_s2d/tools/ – Hilfswerkzeuge

Interne Hilfswerkzeuge, die von `src/wisi_s2d/cli/` und `src/wisi_s2d/web/` importiert werden.

## Dateien

| Datei | Beschreibung |
|---|---|
| `menu.py` | Interaktives Konsolenmenü – Kanalliste, Kanalvorbereitung, Stream-Aufnahme und `.ts`-Entschlüsselung |
| `pcap_parser.py` | PCAP-Parsing (Ethernet & Raw IPv4, inkl. PCAPdroid-Captures), APIX-Befehlserkennung und Statistiken |

## Imports

```python
from wisi_s2d.tools.menu import main_menu
from wisi_s2d.tools.pcap_parser import analyze, packets
```

## Hinweise

- `pcap_parser.analyze()` wird von der Web-UI (`/api/pcap/analyze`) und der CLI (`--pcap`) genutzt.
- Die PCAP-Dateien liegen typischerweise unter `research/assets/` (siehe `research/README.md`).
