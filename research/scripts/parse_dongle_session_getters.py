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

field_ids_size = struct.unpack_from("<I", data, 0x50)[0]
field_ids_off = struct.unpack_from("<I", data, 0x54)[0]
fields = []
for i in range(field_ids_size):
    class_idx, type_idx, name_idx = struct.unpack_from("<HHI", data, field_ids_off + i * 8)
    fields.append((types[class_idx], strings[name_idx]))

class_defs_size = struct.unpack_from("<I", data, 0x60)[0]
class_defs_off = struct.unpack_from("<I", data, 0x64)[0]

target = "Lcom/android/tv/crenova/models/DongleSessionInfo;"

for i in range(class_defs_size):
    off = class_defs_off + i * 32
    class_idx, access_flags, superclass_idx, interfaces_off, source_file_idx, annotations_off, class_data_off, static_values_off = struct.unpack_from("<IIIIIIII", data, off)
    if types[class_idx] == target:
        p = class_data_off
        sf_size, p = read_uleb128(data, p)
        if_size, p = read_uleb128(data, p)
        dm_size, p = read_uleb128(data, p)
        vm_size, p = read_uleb128(data, p)
        for _ in range(sf_size + if_size):
            _, p = read_uleb128(data, p)
            _, p = read_uleb128(data, p)
        mid = 0
        for _ in range(dm_size + vm_size):
            mid_diff, p = read_uleb128(data, p)
            mid += mid_diff
            acc, p = read_uleb128(data, p)
            code_off, p = read_uleb128(data, p)
            m_class, m_name = methods[mid]
            if m_name in ("getDongleSwVersion", "getDongleHwType", "getDongleCustomerId", "getDongleChipId", "setDongleSwVersion", "setDongleHwType", "setDongleCustomerId", "setDongleChipId", "getDongleModelName", "setDongleModelName"):
                print(f"Method {m_name} code_off={code_off}")
                if code_off != 0:
                    insns_size = struct.unpack_from("<I", data, code_off + 12)[0]
                    insns = data[code_off + 16 : code_off + 16 + insns_size * 2]
                    for ip in range(0, len(insns) - 4, 2):
                        op = insns[ip]
                        if op in (0x52, 0x53, 0x54, 0x55, 0x59, 0x5a, 0x5b): # iget / iput
                            fid = struct.unpack_from("<H", insns, ip + 2)[0]
                            print(f"  field: {fields[fid]}")
                        elif op == 0x1a:
                            sidx = struct.unpack_from("<H", insns, ip + 2)[0]
                            if sidx < len(strings):
                                print(f"  const-string: '{strings[sidx]}'")
