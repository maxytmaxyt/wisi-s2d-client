import zipfile
import struct

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

pos = 3817914
print("Context around 3817914:")
sub = data[pos - 200 : pos + 100]

# Let's search all const-string instructions in sub:
# 1a [reg] [str_idx_16]
for i in range(len(sub) - 4):
    if sub[i] == 0x1a:
        sidx = struct.unpack_from("<H", sub, i + 2)[0]
        if sidx < len(strings):
            print(f"  String at -{len(sub)-i}: '{strings[sidx]}'")

print("\nRaw bytes around invoke:")
print(data[pos - 30 : pos + 30].hex())
