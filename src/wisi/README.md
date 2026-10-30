# src/wisi/ – CLI-Einstiegspunkte

Dieses Paket enthält alle CLI-Subkommandos. Einstieg ist `wisi.py`.

## Dateien

| Datei | Beschreibung |
|---|---|
| `wisi.py` | Haupt-CLI – parsed Argumente und delegiert an Submodule |
| `client.py` | Stream-Client (`--stream`), Re-Export von `DEFAULT_IP` |
| `channels.py` | Kanalliste ausgeben (`--channels`) |
| `common.py` | `load_services()`-Helfer – gemeinsam genutzt von mehreren Submodulen |
| `discovery.py` | Experimentelle UDP-Gerätesuche (`--discover`) |
| `epg.py` | EPG aller Sender als JSON exportieren (`--epg`) |
| `menu.py` | Interaktives Konsolenmenü (wird von `client.py` aufgerufen) |
| `pcap.py` | PCAP-Datei analysieren (`--pcap`) |
| `probe.py` | Einzelnen unbekannten Opcode testen (`--probe-opcode`) |

## Imports

Alle Module hier importieren aus dem übergeordneten `src/`-Verzeichnis (flat-module):

```python
import protocol
from channels import fetch_channel_list
from models import ServiceEntry
```

Untereinander importieren sie als `wisi.*`:

```python
from wisi.common import DEFAULT_IP, load_services
from wisi.client import main
```

## Ausführen

```bash
python src/wisi/wisi.py --help
```
