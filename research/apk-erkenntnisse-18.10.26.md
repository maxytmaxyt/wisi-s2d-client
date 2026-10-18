# APK-Analyse: Vollständige UDP-Opcode-Tabelle (Oktober 2026)

Quelle: `com.crenova.tv.dongle.dvb.sdk.messages.CreNovaDongleInitListener` (dekompiliert aus TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk)

## Kritischer Fund: `data_len` bestimmt den Modus, nicht nur der Opcode

Der Dongle unterscheidet zwischen Speedtest und TS-Stream anhand der `data_len` im USBC-Header:
- `data_len = 48128 (0xBC00)` → Dongle antwortet mit **48192 Byte Nutzdaten + 13 USBS = 48205 Byte** (Speedtest-Response)
- `data_len = 0` → Dongle antwortet mit normalem TS-Block (~32740 Byte)

## Vollständige UDP-Befehle aus dem APK (Prefix = 0xF9)

| Methode (APK)                 | Opcode  | data_len | flags | Beschreibung                          |
|-------------------------------|---------|----------|-------|---------------------------------------|
| `onDongleCommunicationStatus` | `0x02`  | 4        | 0x00  | Stream-Init (TCP-Kontext, mit Payload `01 00 00 00`) |
| `e1()`                        | `0x02`  | 0        | 0x00  | Stream-Init (UDP-Kontext, Payload `01 00`) |
| `onSwitchChannel` (ThreadLocal)| `0x01` | 0        | 0x80  | **TS-Block anfordern (data_len=0!)** |
| `e1(bool)` (Pull-Methode)     | `0x01`  | **0xBC00**=48128 | 0x80 | **(Speedtest!** – data_len 48128 → Dongle antwortet mit 48205B) |
| `onGetBouquetListXml()`       | `0x01`  | **0xBC00** | 0x80  | Wie oben – Bytes 8-11: `00 00 BC 00` |
| `onDongleCommunicationStatusHelpText` | `0x03` | 48128 | 0x00 | ? |
| `CreNovaDongleInitListener`   | `0x04`  | 48128    | 0x80  | ? |
| `onDongleGetIntegerData`      | `0x05`  | 48128    | 0x00  | Speedtest (bestätigt aus APK) |
| `onGetChannelBouquetListXml`  | `0x08`  | 48128    | 0x00  | ? |
| `onGetChannelListXml`         | `0x0A`  | 48128    | 0x80  | Speedtest (bestätigt) |
| `onGetChannelInfoXml`         | `0x0B`  | 48128    | 0x00  | ? |

## Der echte TS-Pull: data_len MUSS 0 sein!

```java
// ThreadLocal-Initialisierung des Pull-Buffers:
e1.onDongleGetIntegerData(0, Byte.MIN_VALUE, (byte) -7, (byte) 1);
//                         ^--- data_len = 0 !!
//                              flags = 0x80 (Lesen)
//                              prefix = 0xF9
//                              opcode = 0x01
```

Und die `e1(bool z)`-Methode patcht `byte21` (first/subsequent), aber **überschreibt auch `data_len` auf `0xBC00`**:
```java
bArr[8] = 0;
bArr[9] = 0;
bArr[10] = -68;   // 0xBC
bArr[11] = 0;     // 0x00 → data_len = 0xBC00 = 48128 → SPEEDTEST!
bArr[21] = (byte) onGetChannelExtInfoXml.onDongleCommunicationStatus(z);
```

Das ist der Bug: `e1(bool)` ist für `onGetBouquetListXml` (Speedtest) gedacht, wird aber
in unserem Code als normaler TS-Pull (`cmd_udp_ts_block`) verwendet.

Der echte Pull (ThreadLocal `onSwitchChannel`) hat `data_len = 0` und wird so gebaut:
```
USBC + MAGIC + 00 00 00 00 + 80 00 10 + F9 APIX 01 00...
```

## Fix für protocol.py

```python
def cmd_udp_ts_block(first: bool = False) -> bytes:
    """0xF9/0x01 – MPEG-TS-Block anfordern. data_len MUSS 0 sein!"""
    byte21 = b"\x00" if first else b"\x01"
    return build_usbc(0, 0x80, 0xF9, 0x01, byte21)
    #               ^--- 0, nicht UDP_REQUEST_LEN!
```

## Response-Format bei data_len=0

Wenn `data_len=0` im Request → Dongle antwortet mit ~32740 Byte MPEG-TS-Daten + 13 USBS.
Das ergibt 32753 Byte gesamt. Der USBS-Trailer ist am Ende (letzten 13 Byte).

## Empfangsgröße in DongleCommunicationManager.onGetChannelInfoXml

```java
int i4 = i == 48128 ? i + 64 : i;  // i = data_len aus Request
int i5 = i4 + 13;                   // + USBS-Trailer
byte[] bArr3 = new byte[i5];
this.isType0MMIActive.receive(datagramPacket2);
```
Für data_len=0: empfangt `0 + 0 + 13 = 13` Byte... aber das stimmt nicht mit 32740 überein.
→ Die tatsächliche Antwortgröße wird vom Dongle bestimmt und liegt bei ~32740 Byte.
  Das SDK nimmt was kommt (DatagramPacket nimmt Paketgröße).
