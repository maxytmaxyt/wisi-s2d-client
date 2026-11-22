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

code_off = 3598648
insns_size = struct.unpack_from("<I", data, code_off + 12)[0]
insns = data[code_off + 16 : code_off + 16 + insns_size * 2]

print("Total insns bytes:", len(insns))
ip = 0
while ip < len(insns) - 4:
    op = insns[ip]
    if op == 0x1a:
        sidx = struct.unpack_from("<H", insns, ip + 2)[0]
        if sidx < len(strings):
            print(f"[{ip}] const-string: '{strings[sidx]}'")
    elif op == 0x1b:
        sidx = struct.unpack_from("<I", insns, ip + 2)[0]
        if sidx < len(strings):
            print(f"[{ip}] const-string/jumbo: '{strings[sidx]}'")
    ip += 2
