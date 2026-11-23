# APIX-Protokoll – Befehlsreferenz

> Vollständige technische Dokumentation: [DETAILS.md](DETAILS.md) & [stream.md](stream.md)

## APIX-Befehlsklassen (Übersicht)

| Klasse | Funktionsbereich | Status |
|--------|-----------------|--------|
| **`0xF6`** | Tuner, DVB-S2 LNB/DiSEqC/Satellit, Sendersuchlauf, Kanalwechsel, Kanalliste, Bouquets, EPG, Keep-Alive, Reset | ✅ 100 % verifiziert |
| **`0xF8`** | CAS / Smartcard-MMI, Stream-Stop, Sleep-Mode | ✅ 100 % verifiziert |
| **`0xF9`** | UDP-MPEG-TS-Streaming, AES-128-ECB Link-Crypto, Speedtest | ✅ 100 % verifiziert |
| **`0xFA`** | Hardware-/Session-Info (3-stufig), CI+/SAC-Handshake, Firmware-Flash, OTA-Update | ✅ 100 % verifiziert |
| **`0xFB`** | Werks-/Produktionsmodus | ✅ 100 % dokumentiert |

## 0xF6 – Tuner & Steuerung

| Opcode | Name | Antwort | Implementiert |
|--------|------|---------|--------------|
| `0xF6/0x00` | Reset / Neustart | 2 B | Dokumentiert |
| `0xF6/0x01` | DVB-S2 Transponder-Tune | 32 B | `scan.py` `cmd_dvbs2_tuner_set()` |
| `0xF6/0x02` | Tuner-/Scan-Status | 17 B | `scan.py` `parse_tuner_scan_status()` |
| `0xF6/0x03` | Kanalwechsel per `prog_idx` | 4 B | `prepare.py` `cmd_prepare()` |
| `0xF6/0x07` | DVB-S2 LNB-Konfiguration | 2 B | `scan.py` `cmd_dvbs2_lnb_set()` |
| `0xF6/0x08` | DiSEqC 1.0/1.1/1.2 & USALS | 2 B | `scan.py` `cmd_dvbs2_diseqc_set()` |
| `0xF6/0x09` | Satellitenposition setzen | 2 B | `scan.py` `cmd_dvbs2_satellite_set()` |
| `0xF6/0x10` | Sendersuchlauf starten/stoppen | 2 B | `scan.py` `cmd_scan_start_stop()` |
| `0xF6/0x11` | Suchlauf-Ergebnis: Größe | 4–6 B | `scan.py` `cmd_scan_result_size()` |
| `0xF6/0x12` | Suchlauf-Ergebnis: XML-Daten | variabel | `scan.py` `cmd_scan_result_data()` |
| `0xF6/0x16` | Session-Init / Keep-Alive | 12 B | `protocol.py` `cmd_16()` |
| `0xF6/0x17` | Session-Bestätigung | 4 B | `protocol.py` `cmd_17_init/confirm()` |
| `0xF6/0x20` | Kanallisten-Größe | 8 B | `channels.py` |
| `0xF6/0x21` | Kanalliste (XML) | variabel | `channels.py` `fetch_channel_list()` |
| `0xF6/0x22` | Kanalliste quittieren | 8 B | `channels.py` |
| `0xF6/0x30` | EPG-Größe für `prog_idx` | 6 B | `protocol.py` `cmd_epg_size()` |
| `0xF6/0x31` | EPG-Daten | variabel | `protocol.py` `cmd_epg_data()` |
| `0xF6/0x32` | Kanal-Info-Größe | 6 B | `protocol.py` `cmd_chinfo_size()` |
| `0xF6/0x33` | Kanal-Info (XML) | variabel | `protocol.py` `cmd_chinfo_data()` |
| `0xF6/0x35` | Event-Beschreibung: Größe | 6 B | `protocol.py` `cmd_evtdesc_size()` |
| `0xF6/0x36` | Event-Beschreibung: Daten | variabel | `protocol.py` `cmd_evtdesc_data()` |
| `0xF6/0x40` | Hard-Reset | 2 B | Dokumentiert |

## 0xF8 – Stream & CAS

| Opcode | Name | Antwort | Implementiert |
|--------|------|---------|--------------|
| `0xF8/0x00`–`0x06` | Smartcard-MMI / CAS | variabel | Dokumentiert |
| `0xF8/0x07` | Stream/Aufnahme stoppen | 0 B | `protocol.py` `cmd_stream_release()` |
| `0xF8/0x10`–`0x17` | Smartcard erweitert | variabel | Dokumentiert |

## 0xF9 – UDP-MPEG-TS-Streaming

| Opcode | Name | Anmerkung |
|--------|------|-----------|
| `0xF9/0x01` | TS-Block anfordern (Pull) | Haupt-Pull-Loop; `first=True/False` je nach Retry |
| `0xF9/0x02` | UDP-Stream initialisieren | Einmalig vor dem ersten Pull |
| `0xF9/0x03`, `0x04` | IPTV-Injektion | Dokumentiert |
| `0xF9/0x0A` | Speedtest-Burst | **Kein** Channel-DB – nur Bandbreiten-Messung |

**Link-Verschlüsselung:** Alle TS-Pakete (auch FTA) werden mit AES-128-ECB verschlüsselt.  
Schlüssel: `1234567880ABCDEF1234567880ABCDEF` (aus APK `onDongleCommunicationStatusHelpText`).

## 0xFA – Hardware-Info & CI+/SAC

| Opcode | Name | Antwort |
|--------|------|---------|
| `0xFA/0x00` | Hardware-Info Phase 1 | 64 B (Tuner-Typ, Versionen, Chip-ID, Seriennummer) |
| `0xFA/0x01` | SAC-Antwortlänge abfragen | 6 B |
| `0xFA/0x02` | SAC-Antwortpaket lesen | variabel |
| `0xFA/0x03` | SAC-Anforderung senden | 0 B |
| `0xFA/0x04`–`0x06` | Firmware-Flash | variabel |
| `0xFA/0x07` | Hardware-Info Phase 2 | 51 B (Modellname, SVN-Revision, VSC-ID) |
| `0xFA/0x08` | Hardware-Info Phase 3 | 480 B (MAC, IP, Feature-Flags) |
| `0xFA/0x0A`–`0x19` | OTA-Firmware-Update | variabel |

**CI+/SAC Root-Seed:** `LukeRanDolphCI+1` (aus `libsecure_module.so`, Funktion `SecEngInit`)

## 0xFB – Produktionsmodus

| Opcode | Name |
|--------|------|
| `0xFB/0x01` | Production Data lesen |
| `0xFB/0x02` | XML-Report |
| `0xFB/0x03` | Produktionsmodus aktivieren/deaktivieren |

## Paketstruktur (USBC CBW)

```
Offset  Länge  Inhalt
 0       4     "USBC" (Magic)
 4       4     0xA0CB0337 (WISI Magic Tag)
 8       4     data_len (Big-Endian)
12       1     flags: 0x80=Lesen, 0x00=Schreiben
13       1     0x00
14       1     0x10 (CDB-Länge)
15      16     CDB: [prefix, "APIX", opcode, payload…] (auf 16 B aufgefüllt)
```

Antwort: `data_len` Bytes Nutzdaten + 13-Byte USBS-Trailer (`"USBS"` + Status).
