import zipfile
import struct

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk")) as apk:
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

field_ids_size = struct.unpack_from("<I", data, 0x50)[0]
field_ids_off = struct.unpack_from("<I", data, 0x54)[0]
fields = []
for i in range(field_ids_size):
    class_idx, type_idx, name_idx = struct.unpack_from("<HHI", data, field_ids_off + i * 8)
    fields.append((types[class_idx], strings[name_idx]))

class_defs_size = struct.unpack_from("<I", data, 0x60)[0]
class_defs_off = struct.unpack_from("<I", data, 0x64)[0]

for i in range(class_defs_size):
    off = class_defs_off + i * 32
    class_idx, access_flags, superclass_idx, interfaces_off, source_file_idx, annotations_off, class_data_off, static_values_off = struct.unpack_from("<IIIIIIII", data, off)
    cname = types[class_idx]
    if class_data_off != 0:
        p = class_data_off
        sf_size, p = read_uleb128(data, p)
        if_size, p = read_uleb128(data, p)
        fid = 0
        has_buyer = False
        field_list = []
        for _ in range(sf_size):
            fid_diff, p = read_uleb128(data, p)
            fid += fid_diff
            acc, p = read_uleb128(data, p)
            fname = fields[fid][1]
            field_list.append(fname)
            if "WISI" in fname or "SCHWAIGER" in fname:
                has_buyer = True
        if has_buyer:
            print(f"Class: {cname} has buyer fields! (static_values_off={static_values_off})")
            if static_values_off != 0:
                size, vp = read_uleb128(data, static_values_off)
                for vi in range(size):
                    vh = data[vp]
                    vp += 1
                    vt = vh & 0x1f
                    va = vh >> 5
                    val = 0
                    for bi in range(va + 1):
                        val |= data[vp] << (bi * 8)
                        vp += 1
                    if vi < len(field_list):
                        if any(k in field_list[vi] for k in ["WISI", "SCHWAIGER"]):
                            print(f"  {field_list[vi]} = {val}")
