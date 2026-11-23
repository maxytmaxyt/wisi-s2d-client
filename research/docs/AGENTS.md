# Projekt-Hinweise für Agenten

## Schnellorientierung

Dieses Repo enthält einen vollständig reverse-engineerten (**100 % aller 5 APIX-Klassen**) und live gegen das Gerät verifizierten Python-Client für den **WISI OR S2D / TiViCon DVB-over-IP-Dongle**.

| Was | Wo |
|---|---|
| CLI-Einstieg | `src/wisi_s2d/cli/main.py --help` |
| Datenmodelle | `src/models.py` – `Channel`, `ServiceEntry`, `FALLBACK_SERVICE` |
| Protokoll-Builder | `src/protocol.py` – USBC-Builder, Konstanten, TCP/UDP-Befehlspakete |
| DVB-S2 Scan & SAC (`0xFA`) | `src/scan.py` – LNB/DiSEqC/Satellit/Transponder/Scan (`0xF6/0x01..0x12`), Dongle-Info & SAC (`0xFA/0x00..0x08`) |
| TCP-Verbindung | `src/connection.py` – `recv_exactly`, `send_recv`, `connect`, `disconnect` |
| Kanalliste | `src/channels.py` – `fetch_channel_list`, `parse_chlist_xml` |
| Keep-Alive | `src/keepalive.py` – `_keepalive_worker` |
| Kanalwechsel & Signal | `src/prepare.py` – `prepare_channel` (`0xF6/0x03`, `0x32/0x33`, `0x02`) |
| TS-Entschlüsselung | `src/decrypt.py` – `descramble_ts_block`, `decrypt_ts_file` (AES-128-ECB) |
| Stream-Loop | `src/stream.py` – `stream()` (`0xF9/0x02`, `0xF9/0x01`, `0xF8/0x07`) |
| Menü-Logik | `src/tools/menu.py` – interaktives Konsolenmenü |
| PCAP-Parser | `src/tools/pcap_parser.py` – Ethernet/Raw-IPv4 + APIX-Analyse |
| CLI-Subkommandos | `src/wisi/` – `wisi`, `client`, `channels`, `decrypt`, `epg`, `discovery`, `probe`, `pcap`, `menu` |
| Protokoll-Spezifikation | `research/docs/DETAILS.md` ← **zuerst lesen** |
| Streaming-Ablauf | `research/docs/stream.md` – Schritt-für-Schritt A–Z |

---

## Verifizierter Stand (November 2026 – Protokoll zu 100 % entschlüsselt)

- ✅ **Alle 5 APIX-Befehlsklassen vollständig entschlüsselt:** `0xF6` (Tuner/Scan/Kanalliste/EPG/System), `0xF8` (CAS/MMI & Stream-Sleep `0x07`), `0xF9` (UDP-Stream, IPTV-Inject & Speedtest `0x0A`), `0xFA` (Dongle-Info `0x00/0x07/0x08`, SAC-Handshake `0x01..0x03`, FW-Update/OTA), `0xFB` (Production Mode). Es gibt im SDK **keine** `0xF7`- oder `0xFC..0xFE`-Klassen.
- ✅ **USBC/APIX-Rahmenformat:** 31 Byte CBW + 13 Byte USBS-Trailer; jede TCP-Antwort beginnt mit 2-Byte-Echo `[opcode, subopcode]`
- ✅ **TCP-Init-Sequenz (`connection.py`):** `0xF6/0x16` prüft `r[2] == 0x01` (Geräte-ID in `r[3:8]`), gefolgt von `0xF6/0x17` (`r[2]`)
- ✅ **Senderliste & `0x48xxxxxx`-Bedeutung (`channels.py`, `models.py`):** TCP `0xF6/0x20` + `0xF6/0x21` + `0xF6/0x22` (`data_len = 8`), 440 Kanäle live verifiziert. **`0x40xxxxxx` = TV (`type="TV"`), `0x48xxxxxx` = Radio (`type="RD"`, Bit 27)**; Verschlüsselung wird ausschließlich über `fta="0"` signalisiert!
- ✅ **DVB-S2 Sendersuchlauf (`scan.py`):** Vollständige 7-stufige Sequenz verifiziert und implementiert: `0xF6/0x07` (LNB) → `0xF6/0x08` (DiSEqC/USALS) → `0xF6/0x09` (Satellit) → `0xF6/0x01` (Transponder-Tune, `data_len=32`) → `0xF6/0x10` (Scan Start/Stop) → `0xF6/0x02` (17-Byte Status/Progress-Poll) → `0xF6/0x11` & `0xF6/0x12` (Scan-Resultat-XML)
- ✅ **CI+ / SAC-Handshake & Dongle-Info (`scan.py`):** 3-stufige Hardware-Info (`0xFA/0x00` → `0xFA/0x07` → `0xFA/0x08`) und 3-stufige Diffie-Hellman-/SAC-Zustandsmaschine (`0xFA/0x03` Write → `0xFA/0x01` Poll Len → `0xFA/0x02` Read, Root-Seed `LukeRanDolphCI+1`) vollständig dokumentiert und als Framing-Builder implementiert
- ✅ **EPG & Kanalinfo (`epg.py`, `prepare.py`):** `0xF6/0x30`–`0x36` erwarten den `prog_idx` an USBC-Bytes **25–28**; XML-Antworten beginnen mit 2-Byte-Header (`f6 31` / `f6 33`) und enden mit `\x00`-Padding
- ✅ **Kanalwechsel (`prepare.py`):** `0xF6/0x03` (`cmd_prepare`) benötigt Modus `00 00 00 02` an USBC-Bytes 21–24 sowie `prog_idx` (uint32 BE) an Bytes 25–28; Antwort ist `f6 03 <signalLock> <isFta>`
- ✅ **UDP-Pull-Schleife (`stream.py`):** `0xF9/0x01` mit `byte21 = 0x00` beim ersten Block **und nach jedem erfolgreichen Block**; `byte21 = 0x01` **nur bei Retry nach Timeout/Fehler**; Antwortgröße `48.205 Bytes` (`48.128 B` TS + `64 B` `EXTRACSW` + `13 B` `USBS`), Sequenznummer in `EXTRACSW[12]`
- ✅ **Stream-Teardown (`protocol.py`, `stream.py`):** `0xF8/0x07` (`cmd_stream_release`, 35 Bytes = 31B USBC + `01 00 00 00`) stoppt den Stream und darf **nur beim Beenden** gesendet werden
- ✅ **AES-128-ECB Link-Verschlüsselung (`decrypt.py`):** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`(pkt[3] >> 6) & 3 == 2`) auch bei FTA-Sendern mit `AES/ECB/NoPadding` und dem Schlüssel `1234567880ABCDEF1234567880ABCDEF`

---

## Wichtige Nicht-Ziele / Fallen

- `0xF9/0x0A` ist ein **Speedtest** (`getSpeedTestMbps()`) → niemals als Senderdatenbank dekodieren
- `0x48xxxxxx` im `prog_idx` bedeutet **Radio (`type="RD"`)**, nicht Pay-TV → für Verschlüsselung immer `fta` prüfen
- `0xF8/0x07` und `0xF6/0x01(0)` niemals vor dem UDP-Stream senden (schaltet den Tuner/Demux ab)
- `research/archive/` enthält historische Hypothesen und darf nicht als Implementierungsgrundlage genutzt werden
