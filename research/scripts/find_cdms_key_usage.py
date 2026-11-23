import zipfile
import struct
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        data = apk.read("classes2.dex")

def read_uleb128(b, idx):
    val = 0
    shift = 0
    while True:
        byte = b[idx]
        idx += 1
        val |= (byte & 0x7f) << shift
        if not (byte & 0x80):
            break
        shift += 7
    return val, idx

string_ids_size = struct.unpack_from("<I", data, 0x38)[0]
string_ids_off = struct.unpack_from("<I", data, 0x3C)[0]
strings = []
for i in range(string_ids_size):
    off = struct.unpack_from("<I", data, string_ids_off + i * 4)[0]
    length, idx = read_uleb128(data, off)
    end = data.find(b"\x00", idx)
    strings.append(data[idx:end].decode("latin1", errors="replace"))

s_target = struct.pack("<H", 4879)
for m in re.finditer(re.escape(s_target), data):
    p = m.start()
    if p >= 1 and data[p-1] == 0x1a:
        print(f"const-string CDMS_API_KEY at {p-1}")
        sub = data[p-20:p+80]
        # let's look for other const-strings
        for j in range(len(sub)-4):
            if sub[j] == 0x1a:
                sidx = struct.unpack_from("<H", sub, j+2)[0]
                if sidx < len(strings):
                    print(f"  sub string: '{strings[sidx]}'")
            elif sub[j] == 0x1b:
                sidx = struct.unpack_from("<I", sub, j+2)[0]
                if sidx < len(strings):
                    print(f"  sub string/jumbo: '{strings[sidx]}'")
