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

type_ids_size = struct.unpack_from("<I", data, 0x40)[0]
type_ids_off = struct.unpack_from("<I", data, 0x44)[0]
types = [strings[struct.unpack_from("<I", data, type_ids_off + i * 4)[0]] for i in range(type_ids_size)]

method_ids_size = struct.unpack_from("<I", data, 0x58)[0]
method_ids_off = struct.unpack_from("<I", data, 0x5C)[0]
methods = []
for i in range(method_ids_size):
    class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", data, method_ids_off + i * 8)
    methods.append((types[class_idx], strings[name_idx]))

pos = 2837814
print("Instructions around offset 2837814:")
sub = data[pos - 150 : pos + 100]

for i in range(0, len(sub) - 6, 2):
    op = sub[i]
    if op == 0x1a:
        sidx = struct.unpack_from("<H", sub, i + 2)[0]
        if sidx < len(strings):
            print(f"  str: '{strings[sidx]}'")
    elif op in (0x6e, 0x6f, 0x70, 0x71, 0x72):
        mid = struct.unpack_from("<H", sub, i + 2)[0]
        if mid < len(methods):
            print(f"  inv: {methods[mid]}")
