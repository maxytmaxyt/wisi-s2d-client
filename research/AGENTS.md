# Projekt-Hinweise für Agenten

## Schnellorientierung

Dieses Repo enthält einen reverse-engineerten und live gegen das Gerät verifizierten Python-Client für den **WISI OR S2D / TiViCon DVB-over-IP-Dongle**.

| Was | Wo |
|---|---|
| CLI-Einstieg | `src/wisi/wisi.py --help` |
| Datenmodelle | `src/models.py` – `Channel`, `ServiceEntry`, `FALLBACK_SERVICE` |
| Protokoll-Builder | `src/protocol.py` – USBC-Builder, Konstanten, TCP/UDP-Befehlspakete |
| TCP-Verbindung | `src/connection.py` – `recv_exactly`, `send_recv`, `connect`, `disconnect` |
| Kanalliste | `src/channels.py` – `fetch_channel_list`, `parse_chlist_xml` |
| Keep-Alive | `src/keepalive.py` – `_keepalive_worker` |
| Kanalwechsel & Signal | `src/prepare.py` – `prepare_channel` (`0xF6/0x03`, `0x32/0x33`, `0x02`) |
| TS-Entschlüsselung | `src/decrypt.py` – `descramble_ts_block`, `decrypt_ts_file` (AES-128-ECB) |
| Stream-Loop | `src/stream.py` – `stream()` (`0xF9/0x02`, `0xF9/0x01`, `0xF8/0x07`) |
| Menü-Logik | `src/tools/menu.py` – interaktives Konsolenmenü |
| PCAP-Parser | `src/tools/pcap_parser.py` – Ethernet/Raw-IPv4 + APIX-Analyse |
| CLI-Subkommandos | `src/wisi/` – `wisi`, `client`, `channels`, `decrypt`, `epg`, `discovery`, `probe`, `pcap`, `menu` |
| Protokoll-Spezifikation | `research/DETAILS.md` ← **zuerst lesen** |
| Streaming-Ablauf | `research/stream.md` – Schritt-für-Schritt A–Z |

---

## Verifizierter Stand (November 2026 – live am Gerät bestätigt)

- ✅ **USBC/APIX-Rahmenformat:** 31 Byte CBW + 13 Byte USBS-Trailer; jede TCP-Antwort beginnt mit 2-Byte-Echo `[opcode, subopcode]`
- ✅ **TCP-Init-Sequenz (`connection.py`):** `0xF6/0x16` prüft `r[2] == 0x01` (Geräte-ID in `r[3:8]`), gefolgt von `0xF6/0x17` (`r[2]`)
- ✅ **Senderliste (`channels.py`):** TCP `0xF6/0x20` + `0xF6/0x21` + `0xF6/0x22` (`data_len = 8`), 440 Kanäle live verifiziert
- ✅ **EPG & Kanalinfo (`epg.py`, `prepare.py`):** `0xF6/0x30`–`0x36` erwarten den `prog_idx` an USBC-Bytes **25–28**; XML-Antworten beginnen mit 2-Byte-Header (`f6 31` / `f6 33`) und enden mit `\x00`-Padding
- ✅ **Kanalwechsel (`prepare.py`):** `0xF6/0x03` (`cmd_prepare`) ist der eigentliche Umschaltbefehl (`ACTION_CHANGE_CHANNEL_BY_PROGIDX`) und benötigt Modus `00 00 00 02` an USBC-Bytes 21–24 sowie `prog_idx` (uint32 BE) an Bytes 25–28; Antwort ist `f6 03 <signalLock> <isFta>`
- ✅ **UDP-Pull-Schleife (`stream.py`):** `0xF9/0x01` mit `byte21 = 0x00` beim ersten Block **und nach jedem erfolgreichen Block**; `byte21 = 0x01` **nur bei Retry nach Timeout/Fehler**; Antwortgröße `48.205 Bytes` (`48.128 B` TS + `64 B` `EXTRACSW` + `13 B` `USBS`), Sequenznummer in `EXTRACSW[12]`
- ✅ **Stream-Teardown (`protocol.py`, `stream.py`):** `0xF8/0x07` (`cmd_stream_release`, 35 Bytes = 31B USBC + `01 00 00 00`) stoppt den Stream und darf **nur beim Beenden** gesendet werden (niemals beim Start!)
- ✅ **AES-128-ECB Link-Verschlüsselung (`decrypt.py`):** Der Dongle verschlüsselt alle Elementarstream-TS-Pakete (`(pkt[3] >> 6) & 3 == 2`) auch bei FTA-Sendern mit `AES/ECB/NoPadding` und dem Schlüssel `1234567880ABCDEF1234567880ABCDEF` (`com.crenova.tv.dongle.dvb.sdk.ui.player.a.onDongleCommunicationStatusHelpText`)

---

## Offene optionale Forschungspunkte

1. **Sendersuchlauf-PCAP:** Aufzeichnung eines kompletten DVB-S2-Suchlaufs (`0xF7/0x01`, `0xF8/0x01..0x04`) in der Original-App.
2. **Pay-TV / CI+ (`0x48xxxxxx`):** Vollständige Nachbildung des Diffie-Hellman-/SAC-Handshakes aus `libsecure_module.so` (Root-Seed `LukeRanDolphCI+1`).

---

## Wichtige Nicht-Ziele / Fallen

- `0xF9/0x0A` ist ein **Speedtest** (`getSpeedTestMbps()`) → niemals als Senderdatenbank dekodieren
- `0xF8/0x07` und `0xF6/0x01(0)` niemals vor dem UDP-Stream senden (schaltet den Tuner/Demux ab)
- `research/archive/` enthält historische Hypothesen und darf nicht als Implementierungsgrundlage genutzt werden
