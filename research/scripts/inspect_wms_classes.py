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

class_defs_size = struct.unpack_from("<I", data, 0x60)[0]
class_defs_off = struct.unpack_from("<I", data, 0x64)[0]

target_classes = [
    "Lcom/android/tv/crenova/wms/WmsURI;",
    "Lcom/android/tv/crenova/wms/WmsAPI;",
    "Lcom/android/tv/crenova/models/CheckUpdate;",
    "Lcom/android/tv/crenova/models/DongleSessionInfo;"
]

for i in range(class_defs_size):
    off = class_defs_off + i * 32
    class_idx, access_flags, superclass_idx, interfaces_off, source_file_idx, annotations_off, class_data_off, static_values_off = struct.unpack_from("<IIIIIIII", data, off)
    cname = types[class_idx]
    if cname in target_classes:
        print(f"\n==========================================")
        print(f"CLASS: {cname} (annot={annotations_off})")
        if annotations_off != 0:
            # Let's check method annotations if any
            class_annot_off, fields_size, methods_size, params_size = struct.unpack_from("<IIII", data, annotations_off)
            curr = annotations_off + 16
            for mi in range(methods_size):
                midx, aoff = struct.unpack_from("<II", data, curr)
                curr += 8
                print(f"  Annotated Method: {methods[midx]}")
                asize = struct.unpack_from("<I", data, aoff)[0]
                for aj in range(asize):
                    item_off = struct.unpack_from("<I", data, aoff + 4 + aj * 4)[0]
                    t_idx, p = read_uleb128(data, item_off + 1)
                    num_e, p = read_uleb128(data, p)
                    e_strs = []
                    for _ in range(num_e):
                        n_idx, p = read_uleb128(data, p)
                        vh = data[p]
                        p += 1
                        vt = vh & 0x1f
                        va = vh >> 5
                        if vt == 0x17:
                            s_i = 0
                            for bi in range(va + 1):
                                s_i |= data[p] << (bi * 8)
                                p += 1
                            e_strs.append(f"{strings[n_idx]}='{strings[s_i]}'")
                    print(f"    -> {types[t_idx]} ({', '.join(e_strs)})")
        if class_data_off != 0:
            p = class_data_off
            sf_size, p = read_uleb128(data, p)
            if_size, p = read_uleb128(data, p)
            dm_size, p = read_uleb128(data, p)
            vm_size, p = read_uleb128(data, p)
            # skip fields
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
                if code_off != 0:
                    insns_size = struct.unpack_from("<I", data, code_off + 12)[0]
                    insns = data[code_off + 16 : code_off + 16 + insns_size * 2]
                    # check for const-string
                    strs = []
                    ip = 0
                    while ip < len(insns) - 4:
                        if insns[ip] == 0x1a:
                            sidx = struct.unpack_from("<H", insns, ip + 2)[0]
                            if sidx < len(strings):
                                strs.append(strings[sidx])
                        elif insns[ip] == 0x1b:
                            sidx = struct.unpack_from("<I", insns, ip + 2)[0]
                            if sidx < len(strings):
                                strs.append(strings[sidx])
                        ip += 2
                    if strs:
                        print(f"  Method {m_name}: strings={strs[:10]}")
