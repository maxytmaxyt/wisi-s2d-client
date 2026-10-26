# APK-Analyse: Vollständige UDP-Opcode-Tabelle (Oktober 2026)

Quelle: `com.crenova.tv.dongle.dvb.sdk.messages.CreNovaDongleInitListener` (dekompiliert aus TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk)

## Korrektur: derselbe `data_len` wird für unterschiedliche Kommandos verwendet

Die APK und der Stream-PCAP stimmen hier überein. Der DVB-Worker ruft die `e1(boolean)`-Variante des `F9/01`-Builders auf: Sie setzt `data_len=0xBC00` (48.128) und kodiert den Boolean als Pull-Byte an Offset 21. Der Worker übergibt `0xBC00` als erwartete Datenlänge an `DongleCommunicationManager` und markiert den ersten Block mit `dongle_first_bulk_head`.

Im Stream-PCAP vom 12. Oktober sind 48 UDP-Requests `F9/01` mit genau dieser Headerlänge enthalten: 11 mit Byte 21 = `0x00`, 37 mit Byte 21 = `0x01`. Daneben verwendet der Speedtest separat `F9/0A` mit derselben `data_len=0xBC00`. Die Datenlänge allein unterscheidet die Modi also nicht; Prefix/Opcode und Aufrufpfad tun es.

Der Manager reserviert für den `0xBC00`-Empfangspfad `0xBC00 + 0x40 + 13` Byte. Das ist eine Puffergröße, keine Garantie, dass ein bestimmter Mitschnitt die vollständige TS-Antwort enthält. In der Stream-PCAP ist nur eine 13-Byte-`USBS`-Antwort von Port 8800 sichtbar.

## Vollständige UDP-Befehle aus dem APK (Prefix = 0xF9)

| APK-Variante | Opcode | `data_len` | Flags | Einordnung |
|---|---:|---:|---:|---|
| `onSwitchChannel()`-ThreadLocal-Grundbuilder | `0x01` | `0` | `0x80` | Vorhandene alternative `F9/01`-Variante; für sich allein nicht der im DVB-Worker/PCAP belegte 48-KB-Pfad. |
| `e1(boolean)` im DVB-Worker | `0x01` | `0xBC00` | `0x80` | DVB-Pull; Byte 21 wechselt passend zum Boolean zwischen `0x00` und `0x01`. |
| `onGetChannelListXml()` / Speedtest-Aufrufpfad | `0x0A` | `0xBC00` | `0x80` | Speedtest (`F9/0A`), nicht derselbe Wire-Befehl wie der DVB-Pull. |
| weitere 48-KB-Builder | verschiedene | `0xBC00` | verschieden | Methoden-/Opcode-Namen aus dem obfuskierten SDK sind ohne Aufrufstellen kein hinreichender Beleg für Funktion oder Verwendung. |

## DVB-Pull: im belegten Worker ist `data_len=0xBC00`

```java
// Der Grundbuilder wird für den DVB-Worker kopiert und gepatcht:
e1(boolean firstOrNext);
// Header: data_len=0xBC00, flags=0x80, prefix=0xF9, opcode=0x01
// Byte 21: 0x00 bzw. 0x01 gemäß dem Pull-Zustand
```

Die `e1(boolean)`-Methode patcht sowohl die Länge als auch Byte 21:
```java
bArr[8] = 0;
bArr[9] = 0;
bArr[10] = -68;   // 0xBC
bArr[11] = 0;     // data_len = 0xBC00 = 48128
bArr[21] = (byte) onGetChannelExtInfoXml.onDongleCommunicationStatus(z);
```

Der Worker `onDongleGetIntegerData.tuneChannelByProgIdx()` reicht diesen Request mit der Länge `0xBC00` an `DongleCommunicationManager` weiter; sein Trace enthält `mode=dvb` und `dongle_first_bulk_head`. Der alternative `data_len=0`-Builder existiert ebenfalls, ist aber nicht der im Stream-PCAP sichtbare Pull-Aufruf.
```
USBC + MAGIC + 00 00 BC 00 + 80 00 10 + F9 APIX 01 [byte21...]
```

Die bestehende Python-Implementierung mit `data_len=0xBC00` und Byte 21 = `0x00`/`0x01` passt damit zum beobachteten APK-Worker und zu den ausgehenden Requests im PCAP. Daraus folgt nicht, dass die komplette Antwort oder der vollständige TS-Transport in dieser PCAP aufgezeichnet wurde.

## Empfangspuffer im `DongleCommunicationManager`

```java
int i4 = i == 48128 ? i + 64 : i;  // erwartete Nutzdatenkapazität
int i5 = i4 + 13;                   // zusätzliche 13 Bytes
byte[] bArr3 = new byte[i5];
this.isType0MMIActive.receive(datagramPacket2);
```
Für den `0xBC00`-Pfad ergibt das eine reservierte Empfangsgröße von 48.205 Byte. Diese Allokation erklärt nicht allein den tatsächlichen Antwortinhalt oder die auf dem Kabel beobachtete Paketgröße; die PCAP-Auswertung muss weiterhin Request- und Antwortpakete getrennt behandeln.
