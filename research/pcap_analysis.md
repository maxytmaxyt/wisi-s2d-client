# PCAP-Auswertung

Stand: November 2026. Die Zahlen wurden mit `src/tools/pcap_parser.py` sowie einer vollständigen Rekonstruktion der TCP-Streams und IPv4-fragmentierten UDP-Antworten auf Port 8800 ermittelt.

## Mitschnitte

| Mitschnitt | IPv4-Pakete | `0xF9/0x0A`-Anfragen | Beobachtete Hauptinhalte |
|---|---:|---:|---|
| `assets/capture_pcapdroid_2026-10-11.pcap` | 3.284 | 200 | 198 `0xF9/0x0A`-Antworten (32.740 B) + vollständige EPG-Abfragen (`0xF6/0x30+0x31`, `0x32+0x33`, `0x35+0x36`) |
| `assets/PCAPdroid_12_Okt._16_16_04.pcap` | 940 | 400 | Kanallisten-Abruf (`0xF6/0x20`, `0x21`, `0x22`) mit 440 Sendern (61.348 B XML) |
| `assets/PCAPdroid_12_Okt._16_28_17.pcap` | 1.197 | 200 | Kanalwechsel (`0xF6/0x03`), 48 UDP-Stream-Pulls (`0xF9/0x01`) + 11 fragmentierte 48.205-Byte-TS-Antworten + Teardown (`0xF8/0x07`, `0xF6/0x01`) |

Im Mitschnitt vom 11. Oktober beginnen die großen Antworten mit `f9 0a`; über die gesamten 32.740 Byte sind jeweils nur zwei Bytes ungleich null. Der frühere Legacy-Service-DB-Parser dekodierte daraus null Einträge. Die APK-Analyse ordnet den `F9/0A`-Opcode einem Speedtest zu; sie erklärt nicht bytegenau diese 32.740-Byte-Antworten. Die Antworten der beiden Mitschnitte vom 12. Oktober sind kurze `USBS`-Antworten; dort ist kein großer `0xF9/0x0A`-Blob aufgezeichnet.

Laut separat übermittelter Konsolenausgabe erhielt der Nutzer am 13. Oktober fünfmal eine 48.143-Byte-Antwort mit `f9 0a`-Präfix und Nullbytes am Anfang. Diese Größe taucht in keinem gespeicherten Mitschnitt auf. Die APK-Analyse ordnet sie als Speedtest ein: `getSpeedTestMbps()` baut `0xF9/0x0A` mit 48.128 Byte Testdaten, fordert 48.130 Datenbytes an und berechnet den Durchsatz mit 48.128 Byte pro Antwort. Der SDK-Netzwerkempfänger liest weitere 13 Abschlussbytes: `48.130 + 13 = 48.143`. Das passt zur Konsolenausgabe und ist kein Senderdatenbank-Layout. Ohne Rohblob bleiben Füll- und Abschlussbytes ungeprüft.

## Weitere Beobachtungen

- Die Kanallisten-Aufzeichnung vom 12. Oktober enthält `0xF6/0x20`, `0xF6/0x21` und `0xF6/0x22` über TCP/8802. Das XML wurde in einer separaten Analyse mit 440 Einträgen ausgewertet.
- Der Stream-Mitschnitt enthält `0xF6/0x03`, `0xF6/0x32`, `0xF6/0x33`, `0xF6/0x01`, `0xF8/0x07` und `0xF9/0x01` sowie UDP-Streamverkehr.
- Eine Auswertung der UDP-Requests nach Headerfeldern ergibt im Mitschnitt vom 12. Oktober **48 `0xF9/0x01`-Requests mit `data_len=0xBC00`** (11 mit Byte 21 = `0x00`, 37 mit Byte 21 = `0x01`). Das passt zum APK-DVB-Worker: dessen `e1(boolean)`-Builder setzt genau diese Länge und kodiert den Boolean an Byte 21; der Worker markiert den ersten Block mit `dongle_first_bulk_head`.
- Im selben Mitschnitt sind separat **200 `0xF9/0x0A`-Requests** mit `data_len=0xBC00` enthalten. Dieser Opcode wird im APK-Speedtest benutzt. Die identische Länge allein kennzeichnet also nicht den Modus; Opcode und Aufrufpfad unterscheiden DVB-Pulls (`F9/01`) vom Speedtest (`F9/0A`).
- Der Mitschnitt `16_28_17.pcap` zeigt neben der 13-Byte-`USBS`-Antwort auf `0xF9/0x02` auch **11 vollständige, über IPv4 fragmentierte 48.205-Byte-UDP-Antworten** von Port 8800 (`48.128 B` TS-Daten + `64 B` `EXTRACSW` + `13 B` `USBS`). Da jede 48.205-Byte-UDP-Antwort in 33 IPv4-Fragmente zerlegt ist, sieht ein Parser ohne IPv4-Defragmentierung nur das erste Fragment bzw. die unfragmentierte 13-Byte-`USBS`-Antwort.
- Ebenso zeigt `16_28_17.pcap` eindeutig, dass `byte21 = 0x00` (11×) immer nach einem erfolgreich empfangenen 48.205-Byte-Block gesendet wird und `byte21 = 0x01` (37×) immer nach einem 500-ms-Timeout, sowie dass `0xF8/0x07` (35 B) und `0xF6/0x01(0)` (76 B) erst 20 Sekunden nach dem Tuning beim Verlassen des Streams gesendet werden.
- Die UDP-`0xF9/0x0A`-Requests in den neueren Mitschnitten sind 31 Byte lang; die sichtbaren Antworten sind 13 Byte. Das allein widerlegt oder bestätigt keine anders gerahmten TCP-Kommandos.
- Das APK-SDK erzeugt für `0xF9/0x0A` einen 31-Byte-USBC-Request und verwendet den Opcode im Speedtest. Das ordnet die 48.143-Byte-Antwort ein, ohne die abweichenden 32.740-Byte-PCAP-Antworten gleichzusetzen.

## Grenzen der Auswertung

`src/wisi_pcap.py` liest klassisches PCAP für Ethernet oder Raw IPv4 und extrahiert IPv4-/TCP-/UDP-Payloads. Es verwirft fragmentierte IPv4-Pakete, reassembliert TCP nicht und erkennt APIX-Kommandos durch Suche nach der Signatur `USBC`. Paket- und Kommandazahlen sind daher keine vollständige Rekonstruktion des TCP-Bytestroms. Insbesondere belegen sie kein allgemeingültiges USBS-Trailerformat.

Wiederholbare Analyse:

```bash
python src/wisi.py --pcap "PCAPdroid_12_Okt._16_16_04.pcap"
python src/wisi.py --pcap "PCAPdroid_12_Okt._16_28_17.pcap"
python src/wisi.py --pcap "research/capture_pcapdroid_2026-10-11.pcap"
```
