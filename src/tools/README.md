# src/tools/ – Hilfswerkzeuge

Interne Hilfswerkzeuge, die von `src/wisi/` importiert werden.

## Dateien

| Datei | Beschreibung |
|---|---|
| `menu.py` | Interaktives Konsolenmenü – Senderauswahl, Navigation, Anzeige |
| `pcap_parser.py` | PCAP-Parsing: Ethernet/IP/UDP-Schichten, APIX-Befehlserkennung, Statistiken |

## Imports

```python
from tools.menu import main_menu
from tools.pcap_parser import analyze, packets
```
