# Projekt-Hinweise für Agenten

## Schnellorientierung

Dieses Repo enthält einen reverse-engineerten Python-Client für den **WISI OR S2D / TiViCon DVB-over-IP-Dongle**.

| Was | Wo |
|---|---|
| CLI-Einstieg | `src/wisi/wisi.py --help` |
| Datenmodelle | `src/models.py` – Channel, ServiceEntry, FALLBACK_SERVICE |
| Protokoll-Layer | `src/protocol.py` – USBC-Builder, Konstanten, TCP-Helfer, connect/disconnect |
| Kanalliste | `src/channels.py` – fetch_channel_list, parse_chlist_xml |
| Keep-Alive | `src/keepalive.py` – _keepalive_worker |
| Stream | `src/stream.py` – prepare_channel, stream() |
| Menü-Logik | `src/tools/menu.py` – interaktives Konsolenmenü |
| PCAP-Parser | `src/tools/pcap_parser.py` – Ethernet/IP/UDP + APIX-Analyse |
| CLI-Subkommandos | `src/wisi/` – client, channels, epg, discovery, probe, pcap, menu |
| Protokoll-Spezifikation | `research/DETAILS.md` ← **zuerst lesen** |
| Streaming-Ablauf | `research/stream.md` – Schritt-für-Schritt A–Z |
| Forschungsübersicht | `research/README.md` |
| PCAP-Auswertung | `research/pcap_analysis.md` |
| APK-Befunde | `research/apk_reverse_engineering.md`, `research/apk-erkenntnisse-18.10.26.md` |
| Mitschnitte + Binärdaten | `research/assets/` |
| Veraltete Research-Docs | `research/archive/` |

---

## Belastbarer Stand (Oktober 2026)

- ✅ USBC/APIX-Rahmenformat (31 Byte CBW + 13 Byte USBS-Trailer) bestätigt
- ✅ TCP-Init-Sequenz (`0xF6/0x16` Status-Byte[0]=`0x01`, `0xF6/0x17`) implementiert
- ✅ Senderliste via TCP `0xF6/0x20` + `0xF6/0x21` (XML, 440 Kanäle)
- ✅ EPG via TCP `0xF6/0x30`/`0x31`, `0x32`/`0x33`, `0x35`/`0x36`
- ✅ Signal-Polling via `0xF6/0x02`
- ✅ Tune-Ablauf: `0xF6/0x03` → `0xF6/0x01` → `0xF8/0x07` → `0xF9/0x02` → `0xF9/0x01` (first) → `0xF6/0x17` confirm
- ✅ UDP-Pull-Schleife: `0xF9/0x01` (byte21=`0x01`, kontinuierlich), MPEG-TS Sync-Byte `0x47`
- ✅ UDP-Socket muss lokal auf Port **8800** gebunden sein (vor erstem TCP-Befehl)
- ✅ `0xF9/0x0A` ist ein Speedtest – kein Senderlisten-Befehl
- ✅ `cmd_prepare()` übergibt nur den 4-Byte `prog_idx` (Bytes 21–24)
- ✅ `cmd_tune()` kodiert 16-Bit Kanal-Index Big-Endian (Bytes 21–22)
- ✅ APK statisch analysiert: APIX-Methoden, USBC-Builder, Native-Lib, Hardcoded-Key bekannt
- ✅ Pay-TV-Seed in `libsecure_module.so`: `LukeRanDolphCI+1` (nur für `0x48xxxxxx`-Kanäle)

---

## Erledigte Punkte

### ✅ `0x01`-Payload für Kanalwechsel (Oktober 2026)
Bytes 21–22 = **16-Bit Kanal-Index Big-Endian** (nicht DVB Service-ID, nicht PAT-Array-Index).
`struct.pack(">H", channel_index)` – High-Byte korrekt mitgeschickt bei Index > 255.

### ✅ Stream-Bugs behoben (Oktober 2026)
- `udp.bind(("", protocol.UDP_PORT))` statt Port 0
- `0xF9/0x02` UDP-Init vor erstem Pull eingefügt
- `cmd_prepare()` Payload auf 4 Byte (`prog_idx`) korrigiert (war fälschlicherweise 8 Byte)
- Status-Byte-Index in `connect()` auf `r[0]` korrigiert (war `r[2]`)
- `_keepalive_worker` wird von `keepalive.py` importiert, nicht von `stream.py`

### ✅ `SharedSecret` aus Native-Lib (Oktober 2026)
`libsecure_module.so` enthält `THVrZVJhbkRvbHBoQ0krMQ==` → **`LukeRanDolphCI+1`**.
Root-Key für Pay-TV CI+-Derivation – für FTA irrelevant. Details: `research/apk_reverse_engineering.md`.

---

## Offene Punkte (Priorität)

### 🔴 1 – Livestream live testen
Implementierung ist vollständig, aber noch nicht gegen echten Dongle als Erfolg bestätigt.

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --stream --output - | vlc -
# Bei Problemen:
python src/wisi/wisi.py --ip 192.168.178.32 --stream --output - --debug 2>debug.log | vlc -
```

- PCAP-Vergleich mit `research/assets/PCAPdroid_12_Okt._16_28_17.pcap`
- USBS-Trailer nach jedem TCP-Befehl vollständig lesen (13 Byte)

### 🟡 2 – Scan-PCAP aufzeichnen
Kein Mitschnitt eines Sendersuchlaufs vorhanden. Würde Kanal-Index → LCN-Mapping klären.

```bash
# PCAPdroid auf Android, TV2Smart → Sendersuchlauf → PCAP in research/assets/ ablegen
python src/wisi/wisi.py --pcap research/assets/scan_DATUM.pcap
```

### 🟢 3 – Unbekannte Opcodes per Probe finden
`CMD_GET_ABOUT_DONGLE_INFO`, `CMD_START_SCAN_DVBS` u. a. haben noch keinen bestätigten Opcode-Wert.

```bash
python src/wisi/wisi.py --ip 192.168.178.32 --probe-opcode 0x12
```
Alle Opcodes `0x04`–`0x1F` testen (außer `0x16`/`0x17`). USBS-Status `0x00` = Erfolg.

---

## Wichtige Nicht-Ziele / Fallen

- `0xF9/0x0A` ist **kein** Senderlisten-Befehl → nie als Service-DB dekodieren
- `fetch_service_db()` in `src/wisi/client.py` ist ein **deaktivierter Legacy-Stub** → nicht reaktivieren
- `research/archive/` nicht als Implementierungsgrundlage nutzen
- `research/DETAILS.md` und `research/stream.md` sind die **maßgeblichen Quellen** – bei Widerspruch gewinnen sie
