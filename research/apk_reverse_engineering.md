# TV2Smart: verifizierte APK-Analyse

Statische Analyse des am 14.10.2026 hochgeladenen XAPK. DEX-Methoden wurden mit Androguard disassembliert/dekompiliert; Native-Symbole wurden aus den ARM64-ELF-Dateien gelesen. Das belegt implementierte App-Pfade, nicht automatisch Verhalten auf jedem Dongle oder jeder Firmware.

## Artefakt

| Merkmal | Verifizierter Wert |
|---|---|
| XAPK | `TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk` |
| Paket / Version | `com.tivicon.tv2smart.mobile`, `3.M20260803.0-rev-a14aeb377` |
| Version-Code | `202608030` |
| Android | min API 26, target API 36 |
| Split-Aufbau | Base, `config.arm64_v8a`, `config.xxxhdpi` |
| Base-DEX | `classes.dex`, `classes2.dex`, `classes3.dex` |
| Signatur | v2 und v3; Zertifikats-SHA1 `c61d91b663949e65be1326e58e0c9394daf4a386` |
| XAPK-SHA256 | `c116914f0c66e38c0b1c4318d0c5bd00541b94cc0efd555a54ffc3997e92ff7f` |
| Base-APK-SHA256 | `a8801eb98194e4d35aaf1a8057b761571e87e30d394c2bd4950a8735dd771cd6` |

Der ARM64-Split enthält `libpimbridge.so`, `libpimdec.so`, `libsecure_module.so`, `libvlc.so`, `libvlcjni.so`, `librtmp-jni.so` und `libc++_shared.so`. In diesem XAPK liegen weder `libtivicon_dvb.so` noch `libstream_decoder.so`; diese Namen aus älteren Notizen beschreiben nicht den Inhalt dieses Artefakts.

## APIX-Builder und Speedtest

Die DEX-Klasse `com.crenova.tv.dongle.dvb.sdk.messages.e1` baut einen klassischen USBC-CBW mit **31 Byte** plus optionalem Payload. Der Builder schreibt die Nutzdatenlänge big-endian in Bytes 8–11, Flags in Byte 12, `APIX` in Bytes 16–19, Prefix in Byte 15 und Opcode in Byte 20. In diesem Builder gibt es keine 35-Byte-Erweiterung.

`com.crenova.tv.dongle.dvb.sdk.messages.CreNovaDongleInitListener.onGetChannelListXml()` baut konkret einen Request mit `data_len=48.128`, Flags `0x80`, Prefix `0xF9` und Opcode `0x0A`. Trotz des dekompilierten Methodennamens zeigt die Aufrufstelle die tatsächliche Verwendung: `CrenovaDongleInit.getSpeedTestMbps()` ruft diesen Builder in einer Schleife auf, zählt erfolgreiche Antworten und berechnet den Durchsatz anhand von 48.128 Byte pro Antwort.

Der Netzwerk-Responsepfad wird mit einer erwarteten Datenlänge von 48.130 Byte aufgerufen. Für die 48-KB-Antwort liest er weitere 13 Abschlussbytes und trennt diese vom Datenbereich:

```text
48.130 Datenbytes + 13 Abschlussbytes = 48.143 empfangene Bytes
```

Das erklärt die am 13. Oktober gemeldete Länge und das `f9 0a`-Präfix sehr gut als Speedtest-Antwort, nicht als Senderdatenbank. Der APK-Code interpretiert deren Inhalt nicht als Senderdatensätze. Weil der konkrete Rohblob fehlt, bleiben seine Füllbytes und der 13-Byte-Abschluss bytegenau ungeprüft. Die älteren PCAP-Antworten mit 32.740 Byte sind eine andere Beobachtung und werden durch diesen Codepfad nicht erklärt.

## Kanalliste und Tune-API

- Die vorhandenen OR-S2D-PCAPs zeigen die XML-Kanalliste über TCP `0xF6/0x20` und `0xF6/0x21`. Der APK-Builder enthält mehrere ähnlich benannte Methoden; Methodennamen wie `onGetChannelListXml` reichen allein nicht aus, um ein Wire-Opcode zuzuordnen.
- Das öffentliche SDK-API `tuneChannelByProgIdx(int)` sendet den internen Dispatcher-Auftrag 802. `tuneChannelByProgIdxAndPid(int, int)` sendet Auftrag 808 und akzeptiert genau einen zusätzlichen PID-Integer, nicht separate Video- und Audio-PIDs.
- Der dekompilierte Handler für Auftrag 808 übergibt Program-Index und PID an einen Builder, der einen `0xF6/0x03`-Request mit 10-Byte-Payload konstruiert. Daraus folgt **nicht**, dass diese Werte Bestandteil des im PCAP beobachteten `0xF6/0x01`-Payloads sind.
- Die genaue Zuordnung aller App-internen Tune-Varianten zum OR-S2D-Wireablauf ist aus diesem APK allein nicht abschließend bestätigt. Für `0xF6/0x01` bleibt der Mitschnitt mit Payload `00 04` der direkte Beleg.

## FTA-Stream: bestätigte APK-Bausteine und offene Verkettung

Die folgenden Befunde stammen aus den generischen APIX-Buildern in `messages/e1.smali` und `messages/CreNovaDongleInitListener.smali` sowie dem Transport in `DongleCommunicationManager.smali`. Wegen der Obfuskierung sind Methodennamen allein keine zuverlässige Beschreibung; die konkreten Builder-Argumente und Aufrufstellen sind maßgeblich.

| APK-Baustein | Im Builder/Transport verifiziert | Aussagegrenze |
|---|---|---|
| DVB-Stream-Pull `F9/01` | Der APK-Datenabruf hat eine `e1(boolean)`-Variante, die den Request auf `data_len=0xBC00` (48.128) setzt, das Flags-Byte `0x80` und das Pull-Byte an Offset 21 passend zum Boolean setzt. Der Worker reicht den Request mit Länge `0xBC00` an `DongleCommunicationManager` weiter; sein Trace nennt den Modus „dvb“ und markiert den ersten Block als `dongle_first_bulk_head`. | Ein anderer vorhandener Builder für `F9/01` verwendet `data_len=0`. Dieser Builder allein beschreibt nicht den im PCAP und im DVB-Worker belegten 48-KB-Pfad. |
| Speedtest `F9/0A` | Der Builder setzt `data_len=0xBC00` (48.128), Flags `0x80`, Prefix `0xF9`, Opcode `0x0A`. `CrenovaDongleInit.getSpeedTestMbps()` verwendet diesen Request für den Speedtest. | Gleiche Requestlänge wie beim DVB-Pull, aber anderer Opcode und anderer Aufrufpfad. |
| UDP-Transport | `DongleCommunicationManager` adressiert Datagramme an Port `0x2260` (8800). Für `data_len=0xBC00` reserviert der gezeigte Empfangspfad `0xBC00 + 0x40 + 13` Byte; bei größeren Transfers zerlegt er den Versand in Datagramme. | Die vorhandene Stream-PCAP enthält die ausgehenden Pull-Requests, aber nur eine 13-Byte-Antwort von Port 8800. Sie belegt daher nicht den vollständigen eingehenden MPEG-TS-Block. |
| ExoPlayer-Eingang | Die Player-Hilfsklasse erzeugt mit `ParcelFileDescriptor.createPipe()` eine Pipe. `MpegTsDataSource.read()` liest aus dem zugehörigen `FileInputStream`, begrenzt einen einzelnen Leseaufruf auf maximal `0xBC00` Byte und stellt die Bytes ExoPlayer bereit. | Die Pipe ist eine App-interne Übergabe. Sie identifiziert weder die Quelle der Bytes noch ein APIX-Kommando, Keep-Alive-Intervall oder TS-Blockformat. |

### Ablauf vom Tune bis zum Player-Input: bestätigte Teilstrecken

Die folgende Verkettung unterscheidet zwischen statisch belegten APK-Aufrufen und dem, was die PCAP tatsächlich zeigt. Sie ist keine Behauptung, dass jeder Übergang bereits durch einen einzigen vollständigen Laufzeitmitschnitt bewiesen wurde.

| Phase | Befund | Evidenzgrenze |
|---|---|---|
| Kanalwahl / Tune-API | Das SDK stellt `tuneChannelByProgIdx(int)` bereit und leitet den Aufruf über den internen Dispatcher-Auftrag 802 weiter. Eine Variante mit zusätzlichem PID verwendet Auftrag 808. | Diese SDK-Auftragsnummern sind keine APIX-Wire-Opcodes. Die genaue Zuordnung jedes UI-Ereignisses und jedes SDK-Auftrags zum beobachteten `F6/01`-Payload ist nicht vollständig geschlossen. |
| Dongle vorbereiten | Die Stream-PCAP enthält Tune-/Vorbereitungskommandos einschließlich `F6/03`, `F6/01` und `F8/07`; die allgemeine Projektanalyse ordnet sie dem Wechsel und der Vorbereitung vor dem Pull zu. | Die PCAP-Opcode-Zählung allein bildet weder den gesamten TCP-Bytestrom noch sämtliche Aufrufstellen ab. Sie beweist nicht, dass diese drei Pakete in jedem App-/Firmwarezustand identisch ablaufen. |
| DVB-Daten anfordern | Der DVB-Worker baut mit `e1(boolean)` wiederholt `F9/01`-Requests mit `data_len=0xBC00`. Im Worker wird der Boolean nach dem Abrufzustand umgeschaltet; das ergibt die im Mitschnitt gezählten Werte `00` und `01` an Byte 21. | Im vorhandenen Mitschnitt sind 48 Requests, aber keine dazu passenden vollständigen großen TS-Antworten sichtbar. |
| Antwort auswerten | Der Manager reserviert für die erwartete Länge `0xBC00` einen Empfangspuffer von `0xBC00 + 64 + 13 = 48.205` Byte. Der Rückgabepfad legt Nutzdaten unter `DCM_RES_BUNDLE_KEY_DATA` und weitere Abschlussfelder unter `DCM_RES_BUNDLE_KEY_EXTRACSW` sowie dem CSW-Feld ab. | Die Pufferallokation und Bundle-Aufteilung beschreiben die Implementierung, nicht die tatsächlich übertragene Länge eines bestimmten PCAP-Pakets. Die 64 Zusatzbytes sind hier als separates SDK-Feld belegt; ihre interne Semantik wird nicht weiter interpretiert. |
| Queue / Player-Pipe | Der DVB-Worker liest `DCM_RES_BUNDLE_KEY_DATA` und bietet dieses Byte-Array der blockierenden Queue an. Der Trace-Marker `stream_first_received_queue_offer` protokolliert Länge und Ergebnis des ersten Queue-Angebots. Der Player-Helfer erzeugt eine `ParcelFileDescriptor`-Pipe; `MpegTsDataSource.read()` liest die gegenüberliegende Seite über einen `FileInputStream` und gibt Daten an ExoPlayer weiter. | Die Smali-Stellen belegen die Übergabegrenzen, aber der vorhandene PCAP enthält nicht den großen Antwortblock, mit dem sich die Bytes Ende-zu-Ende gegen die Player-Ausgabe prüfen ließen. |

#### Interpretation der Antwortgröße

`0xBC00` ist 48.128 Byte und bezeichnet im beobachteten `F9/01`-DVB-Worker die angeforderte Datenlänge. Die 64 Byte und 13 Byte kommen in der Empfangsbuffer-/Trailer-Behandlung zusätzlich hinzu. Somit ist die reservierte Gesamtkapazität 48.205 Byte; sie darf nicht als gemessene TS-Nutzdatenlänge oder als Beleg für 48.205 übertragene Bytes ausgegeben werden. Der `F9/0A`-Speedtest ist davon getrennt: gleiche Requestlänge, eigener Opcode und eigener Aufrufpfad.

Die Stream-PCAP vom 12. Oktober enthält 48 ausgehende `F9/01`-Requests und eine sichtbare 13-Byte-`USBS`-Antwort von Port 8800. Aus den verfügbaren Rohdaten ist nicht entscheidbar, ob große Antworten während der Aufzeichnung fehlten, durch Filterung/Verlust nicht in der Datei landeten oder in diesem konkreten Lauf nicht ankamen. Keine dieser Erklärungen wird als Tatsache angenommen. Für einen belastbaren Ende-zu-Ende-Abgleich wird ein neuer Mitschnitt benötigt, der den UDP-Verkehr in beide Richtungen und möglichst gleichzeitig die App-Traces erfasst.

#### Keep-Alive: drei Dinge getrennt halten

1. **TCP-Socketoption:** Der Verbindungsaufbau des `DongleCommunicationManager` ruft `Socket.setKeepAlive(true)` auf. Das aktiviert den vom Betriebssystem verwalteten TCP-Keepalive; es belegt weder einen APIX-Request noch ein bestimmtes Intervall oder eine Dongle-seitige Anwendungsauswirkung.
2. **APIX-Kommandos:** `F6/16` ist im Initialisierungs-/Verbindungskontext sichtbar. Aus seinem Auftreten allein folgt kein periodischer Stream-Keepalive. Für die geprüfte Stream-PCAP ist bislang kein mit Zeitintervall und APK-Aufrufstelle bestätigter periodischer APIX-Heartbeat dokumentiert.
3. **SDK-Service-Kommandos:** Namen wie `CMD_KEEP_ALIVE_STBMODE_RESET` stammen aus dem internen Dispatcher-/Service-Namensraum. Ohne nachgewiesene Zuordnung zu einem konkreten Wire-Request sind sie weder mit `F6/16` noch mit TCP-Keepalive gleichzusetzen.

#### Nächste Evidenz, die den Ablauf schließen würde

- Einen vollständigen Live-Start mit gleichzeitigem App-Trace und PCAP aufnehmen: Kanalwahl, Tune, erste `F9/01`-Requests, große UDP-Antworten und Beginn der Player-Ausgabe zeitlich korrelieren.
- Bei der PCAP-Auswertung Request- und Antworttuple (Quell-/Ziel-IP und -Port), UDP-Länge, APIX-/USBS-Felder und Zeitabstände getrennt erfassen. Ein Zähler von APIX-Signaturen allein reicht nicht zum Request/Response-Matching.
- Den periodischen Keep-Alive nur dann dokumentieren, wenn ein wiederholter Wire-Request zeitlich belegt und mit einer APK-Aufrufstelle verknüpft ist; bis dahin bleiben Intervall und konkreter Befehl offen.

Der beim ExoPlayer-Pfad verwendete Crypto-Helper enthält AES-Encrypt-/Decrypt-Aufrufe mit `AES/ECB/PKCS5Padding`. Aus den statisch verfolgten Stellen ist nicht belegt, ob diese Transformation auf einen FTA-Feed, einen geschützten OTT-Feed oder einen anderen Datenpfad angewendet wird. Daher werden daraus weder Schlüssel noch Klartext- oder Umgehungsschritte abgeleitet.

Die zuvor angenommene Unvereinbarkeit zwischen APK und PCAP bestand nicht: Die APK enthält mehrere `F9/01`-Buildervarianten. Der im DVB-Worker verwendete `e1(boolean)`-Pfad setzt `data_len=0xBC00`, und der Stream-Mitschnitt zeigt genau diese Variante. In `PCAPdroid_12_Okt._16_28_17.pcap` wurden 48 UDP-Requests `F9/01` mit `data_len=48128` gezählt: 11 mit Pull-Byte `00` und 37 mit Pull-Byte `01`. Daneben sind 200 Requests `F9/0A` mit derselben Datenlänge vorhanden; diese gehören zum Speedtest-Aufrufpfad. `data_len` allein unterscheidet daher nicht zwischen Stream und Speedtest; Opcode und Aufrufpfad sind entscheidend.

**Noch offen:** Die Aufzeichnung belegt die Anforderungsschleife, aber nicht den eingehenden MPEG-TS-Block: In der PCAP-Auswertung erscheint nur eine 13-Byte-`USBS`-Antwort auf Port 8800. Ebenso ist ein periodischer APIX-Keep-Alive während des Players aus den bisher verglichenen Bytes nicht nachgewiesen. `F6/16` beim Verbindungsaufbau und App-Service-Kommandos wie `CMD_KEEP_ALIVE_STBMODE_RESET` dürfen ohne passenden Zeit-/Aufrufnachweis nicht als derselbe periodische Stream-Keep-Alive behandelt werden.

## PIM und Sicherheit

`PimCarouselClient` startet getrennte Multicast-Empfänger für EPG-XML und JSON-Nachrichten (`chanmap`/`echan`). Die JSON-Kanalmetadaten enthalten unter anderem `major`, `minor`, Name, IP und Port. PIM-Streams werden als `udp://IP:Port` geöffnet; `PimDataSource` richtet eingehende TS-Daten an 188-Byte-Grenzen aus und ruft `PimNative.decode()` auf.

`PimNative.init(customerCode, pmtPid)` ruft nativ erst `nativeInit(customerCode)` und danach `nativeSetPmtPid(pmtPid)` auf. `libpimbridge.so` exportiert die JNI-Wrapper und bindet die Symbole `pim_custom_init`, `pim_set_pmt_pid`, `pim_set_key`, `pim_status` und `pim_decode` ein. Das belegt einen separaten proprietären PIM-Entschlüsselungspfad in der App, aber keine Kombination dieses Pfads mit dem beobachteten OR-S2D-APIX-Tune-Befehl.

Das DEX enthält außerdem `SecureNativeModule` mit JNI-Methoden für Authentifizierungs-/DH-/SAC-Nachrichten und die ARM64-Datei `libsecure_module.so`. Das belegt, dass die App CI+-artige Sicherheitsfunktionen mitbringt. Es beweist weder, dass diese Funktionen beim WISI OR S2D verwendet werden, noch einen bestimmten APIX-Shared-Secret- oder Challenge-Response-Algorithmus. Die früher notierte Formel `MD5(Challenge || SharedSecret || Timestamp)` ist durch diese APK-Analyse nicht bestätigt.

## ADB-Debugging-Sicherheitscheck

Der USB-Dongle-SDK-Pfad prüft vor der Kommunikation den globalen Android-Wert `Settings.Global["adb_enabled"]`. Die Abfrage liefert „aktiv“, wenn der Wert `1` ist. Im selben Startpfad führt ein positiver Sicherheitscheck zur SDK-Meldung `MSG_COMMUNICATION_FAILED_ADB_DEBUG`.

`DongleCheckActivity` behandelt diese Meldung ausdrücklich: Die UI zeigt „Security check: FAILED! Please turn off DEBUGGING mode in Developer Options“, öffnet über `android.settings.APPLICATION_DEVELOPMENT_SETTINGS` die Entwickleroptionen und beendet die App beim Wechsel in den Hintergrund. Falls Android die Einstellungsseite nicht öffnen kann, erklärt ein Ersatzdialog, wie USB-Debugging manuell deaktiviert wird.

**Praktische Folge:** USB-Debugging in den Entwickleroptionen ausschalten und TV2Smart anschließend neu starten. Der Bytecode enthält zusätzliche Modell-/Statusbedingungen; die Aussage beschreibt daher den nachgewiesenen Prüfpfad dieser APK, nicht ausnahmslos jedes Gerät oder jede Firmware. Die statische Analyse belegt außerdem nicht, ob „Wireless debugging“ auf jeder Android-TV-Version denselben `adb_enabled`-Wert beeinflusst.

## Weitere JADX-Funde aus der Master-Analyse

Die folgenden Details ergänzen die vorherige Gemini-Dokumentation. APK-interne Ressourcen und Konstanten belegen, dass die App diese Funktionen enthält; daraus folgt nicht automatisch, dass sie auf einem WISI OR S2D aktiv oder mit dessen Wire-Protokoll kompatibel sind.

### Versteckte Firmware-Entwickleroptionen

`about_dongle_advanced.xml` definiert den Schalter `prefs_about_dongle_fw_update_dev_enable` und das URL-Feld `prefs_about_dongle_fw_update_dev_url`; beide Ressourcen sind standardmäßig unsichtbar. `AboutDongleAdvancedFragment` schaltet ihre Sichtbarkeit abhängig von `DongleSessionInfo.isDongleUpdateDevEnabled()`. Die Entwicklungs-Update-URL hat den eingebetteten Standardwert `http://192.168.2.80:8080`; die Preferences speichern die URL zusätzlich unter `updateUrlDEV`.

Daneben existiert ein separates `upgrade_debug_fw_switch`-Steuerelement in einem Dialog von `AboutDongleActivity`, das den Debug-Firmware-Zustand aus `AppSettings` liest. `HiddenSettingsActivity` ist im Manifest deklariert. Diese Stellen belegen die entsprechenden UI- und Preference-Pfade, aber nicht, dass die vom Gemini-Bericht genannte 5–7-Tap-Sequenz der einzige oder tatsächlich funktionierende Freischaltweg ist. Ein direkter ADB-Start der Activities ist ebenfalls nicht als allgemein verfügbar bestätigt; Exportstatus und Laufzeitverhalten sind gesondert zu prüfen.

### SDK-Befehle, PIM-Multicast und Endpunkte

`ServiceListCommands` enthält unter anderem interne SDK-IDs `CMD_CHANGE_CHANNEL_BY_PROGIDX = 0x322`, `CMD_CHANGE_CHANNEL_BY_PROGIDX_AND_PID = 0x328`, `CMD_CHANGE_CHANNEL_BY_SID_AND_PID = 0x329`, `CMD_ENABLE_RECORDING = 0x32A` sowie `CMD_SECURE_CH_START_AUTH = 0x12D` und `CMD_SECURE_CH_START_SAC_KEYING = 0x12E`. Das sind Werte aus dem SDK-Dispatcher-Namensraum; sie sind **nicht** ohne zusätzliche Zuordnung als APIX-/TCP-Wire-Opcode zu behandeln. Gleiches gilt für App-Kommandostrings wie `CMD_KEEP_ALIVE_STBMODE_RESET`, `CMD_PLAYER_REC` und `CMD_PLAY_RECORDING`.

Die App setzt für `PimCarouselClient` die Multicast-Gruppe `226.100.0.200` als Default. Das bestätigt eine PIM-Multicast-Konfiguration, aber weder, dass der Dongle selbst an diese Adresse streamt, noch die behauptete Ein-Tuner-Beschränkung oder Mehrgeräte-Wiedergabe desselben Senders.

Der dekodierte Code enthält außerdem Cloud-Basis-URLs unter `https://cdms.tiviconsolutions.com`. Die Klasse `Subscription` baut lokale Client-URLs mit dem eingebetteten Präfix `http://10.20.0.1:5241/Client/Channels/` und `/Client/Subscription/` auf und hängt die Dongle-Chip-ID an. Das ist ein APK-Befund; es bestätigt nicht die im Gemini-Bericht genannte Geräte-IP `192.168.178.32` oder die dort angegebenen Live-Stream- und WMS-Endpunkte. Diese sind nicht als allgemeingültige Endpunkte dieser APK verifiziert.

### Lokale SQLite-Datenbank

Der Datenbank-Handler legt `dongleChListDB.db` an. Im APK-Schema sind unter anderem folgende Tabellen nachgewiesen:

| Tabelle | Inhalt laut Schema |
|---|---|
| `channels` | Kanaltyp/-kategorie, `s_id`, `ts_id`, `prog_idx`, Frequenz, LCN, FTA/Favorit/Sperre, Video-/Audio-/PCR-PIDs sowie optionale IP-/OTT- und Tunerparameter |
| `programs` | EPG-Titel, UTC-Start/-Ende/-Dauer, Kurz-/Langbeschreibung, `prog_idx` und `ts_id` |
| `apk_customization` | UI-/Feature-Schalter, WMS- und Kanallisten-Konfiguration |
| `bouquets`, `user_bouquets` | Bouquet- und Benutzer-Bouquet-Zuordnungen |
| `reminder`, `lockfav`, `ch_set_table`, `fav_table`, `lcnConflict` | Erinnerungen, Favoriten-/Sperrzustand, Kanaloptionen und LCN-Konflikte |

Das ist das Schema der App-Datenbank; es belegt nicht, dass diese Tabellen direkt auf dem Dongle gespeichert werden.

### Aufnahme- und Wiedergabepfade

Im DEX stehen der Aufnahmepfad `Download/TiViConRecordings/` sowie der interne Cache-Pfad `/data/data/com.crenova.tv.dongle/cache/grab_TO_dongle.ts`. Diese Strings belegen referenzierte App-Pfade, aber nicht, dass jede TV2Smart-Installation dort erfolgreich schreiben kann oder dass die Aufnahmefunktion mit dem OR S2D funktioniert.

**Nicht als verifiziert übernommen:** Die Gemini-Aussagen über genau einen physischen DVB-Tuner, `CMD_FORCE_CH_SWITCH`/`CMD_PLAYER_BLOCK_PLAYBACK` als belegte Verdrängungssequenz, den Stream-Endpunkt `http://192.168.178.32:5241/live/ch<s_id>.ts`, einen WMS-Dienst auf Port 8080 und das Verhalten mehrerer Clients. Die dafür nötigen Hardware-/Firmware- oder Mitschnittbelege liegen in der APK allein nicht vor.

## Native-Library-Analyse (15. Oktober 2026)

Die ARM64-Bibliotheken aus `config.arm64_v8a.apk` wurden mit `strings` und `nm` statisch ausgelesen. Die Analyse wurde ohne Laufzeitumgebung durchgeführt und belegt keine Ausführung auf echtem Gerät.

### Übersicht der Native-Libs

| Datei | Größe | Funktion |
|---|---|---|
| `libsecure_module.so` | 229 KB | CI+-artige Content-Control-Auth (SAC/CC-Protokoll, DH-Key-Exchange) |
| `libpimbridge.so` | 5,4 KB | JNI-Wrapper für PIM-Entschlüsselung (ruft `libpimdec.so` auf) |
| `libpimdec.so` | 68 KB | Eigentlicher PIM-Decoder (proprietäre CA-Entschlüsselung, Key-Table aus `libpimbridge.so`) |
| `librtmp-jni.so` | 90 KB | RTMP-Streaming (für externe Streams, nicht OR S2D APIX) |
| `libvlc.so` / `libvlcjni.so` | 44 MB / 94 KB | VLC-Player-Core; `libvlc.so` enthält MD5-Implementierung für interne Zwecke |

### Hardcodierter String in `libsecure_module.so`

In der `.rodata`-Sektion von `libsecure_module.so` wurde ein Base64-kodierter String gefunden, der direkt über dem `CCMSG_CreateAuthReqNoncePacket`-Symbol steht:

```
THVrZVJhbkRvbHBoQ0krMQ==  →  dekodiert: LukeRanDolphCI+1
```

**Kontext im Binary:**
```
CCMSG_CreateAuthReqNoncePacket    ← Symbol (Nonce-Paket-Builder)
Chunk- %s
AUTH_SEND_NONCE
THVrZVJhbkRvbHBoQ0krMQ==         ← Base64-String im .rodata
%02X
nonce
```

Der String liegt im Nur-Lese-Datensegment, nicht auf dem Stack oder in einer Funktion. Er wird wahrscheinlich als statisches Argument an `CNKEY_Init()` oder `SECTK_Initialise()` übergeben, die beide am Anfang der Init-Kette stehen.

**Weitere relevante Symbole in derselben Lib:**
- `CNKEY_Init`, `CNKEY_GetHostKey`, `CNKEY_CalculateRootKey` – Key-Derivation-Chain
- `SECTK_GenerateDhKeys`, `SECTK_CalculateDhShared`, `SECTK_CheckDhPublicKey` – Diffie-Hellman-Schlüsselaustausch
- `SECTK_Sha256`, `CE_Sha256`, `CE_Sha1` – Hashfunktionen (kein MD5 in dieser Lib)
- `SECTK_AesEncrypt`, `SECTK_AesCbcEncrypt` – AES-Verschlüsselung des SAC-Kanals
- Chunk-Keys: `dh_g`, `dh_p`, `dh_q` – DH-Parameter (in `.rodata`, Werte binär kodiert)
- Debugpfad: `/home/paul/ANDROID/Android-Studio-Projects/CreTV/tivicon-dvb-sdk-internal-network-eventbus/...` – bestätigt CreNova als Hersteller

### Einordnung: Wofür wird das gebraucht?

Das CI+-artige SAC/CC-Protokoll in `libsecure_module.so` ist für **Pay-TV / Conditional Access** zuständig, nicht für normales FTA-Streaming. Die Package-Struktur bestätigt das eindeutig:

- `com.crenova.tv.dongle.dvb.sdk.cas.*` – CAS = **Conditional Access System**
- `com.crenova.tv.dongle.dvb.sdk.security.*` – Sicherheits-Layer für CA
- `SecureNativeModule` mit `msgCreateAuthReqNoncePacket`, `msgCreateCCSACKeyingReqPacket` etc. – SAC = Secure Authenticated Channel (CI+-Protokoll)

**Für FTA-Streaming (Schritt 1–3 im normalen Ablauf) wird `libsecure_module.so` nicht benötigt.**

`LukeRanDolphCI+1` ist wahrscheinlich ein **Root-Key oder Seed** für die CNKEY-Derivation-Chain, die ausschließlich im CA-Pfad (Pay-TV) aktiv wird. Die bisherigen PCAPs zeigen keine CC/SAC-Handshake-Pakete im normalen Stream-Betrieb – was zu FTA-Kanälen passt.

### Was `libpimbridge.so` / `libpimdec.so` macht

PIM (Programme Integration Module) ist ein separater proprietärer CA-Pfad über Multicast-UDP. `PimCarouselClient` empfängt Kanal-Metadaten per Multicast (`chanmap`/`echan` als JSON), öffnet UDP-Streams und ruft `pim_decode()` mit den TS-Paketen auf. Das ist **unabhängig vom APIX/USBC-Protokoll** und nicht Teil des OR S2D Streaming-Pfads.

### Fazit für den Client

| Frage | Antwort |
|---|---|
| Braucht normales FTA-Streaming die CC/SAC-Auth? | **Nein.** Kein SAC-Handshake in FTA-PCAPs sichtbar. |
| Was ist `LukeRanDolphCI+1`? | Root-Key/Seed für CI+-artige Pay-TV-Authentifizierung (CNKEY-Chain). |
| Braucht man `libsecure_module.so` für den Python-Client? | Nur wenn verschlüsselte Kanäle (`0x48xxxxxx`-prog_idx) geöffnet werden sollen. |
| War die Formel `MD5(Challenge || SharedSecret || Timestamp)` korrekt? | **Nicht bestätigt.** `libsecure_module.so` verwendet SHA-256 und AES, kein MD5 im CC-Pfad. |

## Korrigierte Aussagen und verbleibende Grenzen

| Frühere Aussage | Ergebnis aus dem hochgeladenen Artefakt |
|---|---|
| `0xF9/0x0A` ist eine Senderdatenbank oder EPG-Abfrage | Nicht bestätigt. Der konkrete APK-Aufruf ist ein Speedtest mit 48.128 Testbytes. |
| Die 48.143 Byte sind ein dekodierbarer Kanalblob | Sehr wahrscheinlich Speedtest-Antwort: 48.130 Datenbytes plus 13 Abschlussbytes. Null-/Füllmuster nicht roh geprüft. |
| Alle APK-Requests sind 66 Byte lang | Falsch für den eingebetteten generischen Builder: er erzeugt 31-Byte-USBC-Requests. Andere Mitschnitte/Transportpfade können abweichen. |
| `...ByProgIdxAndPid` liefert Program-Index plus Video- und Audio-PID | In diesem SDK hat die Methode zwei Integer-Parameter insgesamt: Program-Index und einen PID-Wert. |
| Die App enthält `libtivicon_dvb.so` und `libstream_decoder.so` | Diese Bibliotheken fehlen im hochgeladenen XAPK. |
| Die APK beweist den OR-S2D-`0xF6/0x01`-Payload | Nein. Dafür bleibt der vorhandene PCAP mit Payload `00 04` der direkte Beleg. |

Statische Analyse kann Bytecodepfade zeigen, aber keine Live-Ausführung des SDKs auf dem OR S2D ersetzen. Das 48.143-Byte-Rohpaket wäre weiterhin nötig, um einzelne Payload- und Footerbytes zu verifizieren.
