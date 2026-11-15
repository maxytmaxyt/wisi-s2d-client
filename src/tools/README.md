# src/tools/ – Hilfswerkzeuge

Interne Hilfswerkzeuge, die von `src/wisi/` importiert werden.

## Dateien

| Datei | Beschreibung |
|---|---|
| `menu.py` | Interaktives Konsolenmenü – Kanalliste, Kanalvorbereitung, Stream-Aufnahme und `.ts`-Entschlüsselung |
| `pcap_parser.py` | PCAP-Parsing (Ethernet & Raw IPv4, inkl. PCAPdroid-Captures), APIX-Befehlserkennung und Statistiken |

## Imports

```python
from tools.menu import main_menu
from tools.pcap_parser import analyze, packets
```
