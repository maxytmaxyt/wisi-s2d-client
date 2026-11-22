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

# WmsAPI annot: 8293352
annot_off = 8293352
class_annot_off, fields_size, methods_size, params_size = struct.unpack_from("<IIII", data, annot_off)
curr = annot_off + 16
for mi in range(methods_size):
    midx, aoff = struct.unpack_from("<II", data, curr)
    curr += 8
    m_class, m_name = methods[midx]
    if m_name == "checkUpdUpdate":
        print(f"Found method {m_class}->{m_name}")
        asize = struct.unpack_from("<I", data, aoff)[0]
        for aj in range(asize):
            item_off = struct.unpack_from("<I", data, aoff + 4 + aj * 4)[0]
            t_idx, p = read_uleb128(data, item_off + 1)
            print(f"  Annotation: {types[t_idx]}")
            num_e, p = read_uleb128(data, p)
            for _ in range(num_e):
                n_idx, p = read_uleb128(data, p)
                vh = data[p]
                p += 1
                vt = vh & 0x1f
                va = vh >> 5
                print(f"    element {strings[n_idx]}, vt={vt}, va={va}")
                if vt == 0x1c: # array
                    arr_size, p = read_uleb128(data, p)
                    print(f"      array size: {arr_size}")
                    for elem_i in range(arr_size):
                        evh = data[p]
                        p += 1
                        evt = evh & 0x1f
                        eva = evh >> 5
                        if evt == 0x17: # string
                            si = 0
                            for bi in range(eva + 1):
                                si |= data[p] << (bi * 8)
                                p += 1
                            print(f"        [{elem_i}]: '{strings[si]}'")
