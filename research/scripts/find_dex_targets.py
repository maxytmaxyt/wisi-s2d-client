import zipfile
import struct

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        data = apk.read("classes2.dex")

def parse_dex_strings(dex_bytes):
    string_ids_size = struct.unpack_from("<I", dex_bytes, 0x38)[0]
    string_ids_off = struct.unpack_from("<I", dex_bytes, 0x3C)[0]
    strings = []
    for i in range(string_ids_size):
        off = struct.unpack_from("<I", dex_bytes, string_ids_off + i * 4)[0]
        # read uleb128 length
        idx = off
        length = 0
        shift = 0
        while True:
            b = dex_bytes[idx]
            idx += 1
            length |= (b & 0x7f) << shift
            if not (b & 0x80):
                break
            shift += 7
        # string data up to null
        end = dex_bytes.find(b"\x00", idx)
        s = dex_bytes[idx:end].decode("latin1", errors="replace")
        strings.append(s)
    return strings

strings = parse_dex_strings(data)
print("Total strings:", len(strings))
targets = [
    "checkUpdData", "checkUpdUpdate", "checkUpdateData", "checkUpdateDev",
    "OnLineDongleInfo", "CdmsApi", "UpdateDongleProcessActivity", "UpdateDataModel"
]
for target in targets:
    for idx, s in enumerate(strings):
        if target in s:
            print(f"String [{idx}]: {s}")
