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

proto_ids_size = struct.unpack_from("<I", data, 0x48)[0]
proto_ids_off = struct.unpack_from("<I", data, 0x4C)[0]
protos = []
for i in range(proto_ids_size):
    shorty_idx, return_type_idx, parameters_off = struct.unpack_from("<III", data, proto_ids_off + i * 12)
    param_types = []
    if parameters_off != 0:
        param_size = struct.unpack_from("<I", data, parameters_off)[0]
        for p in range(param_size):
            type_idx = struct.unpack_from("<H", data, parameters_off + 4 + p * 2)[0]
            param_types.append(types[type_idx])
    protos.append((strings[shorty_idx], types[return_type_idx], param_types))

method_ids_size = struct.unpack_from("<I", data, 0x58)[0]
method_ids_off = struct.unpack_from("<I", data, 0x5C)[0]
# Method #27590
class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", data, method_ids_off + 27590 * 8)
shorty, ret_type, p_types = protos[proto_idx]
print(f"Method 27590: {types[class_idx]}->{strings[name_idx]}")
print(f"  Return: {ret_type}")
print(f"  Params: {p_types}")

# Parameter annotations at 8236936
aoff = 8236936
pref_size = struct.unpack_from("<I", data, aoff)[0]
print("  Param annot count:", pref_size)
for pidx in range(pref_size):
    pset_off = struct.unpack_from("<I", data, aoff + 4 + pidx * 4)[0]
    print(f"    Param #{pidx} (type={p_types[pidx]}): pset_off={pset_off}")
    if pset_off != 0:
        psize = struct.unpack_from("<I", data, pset_off)[0]
        for pj in range(psize):
            pitem_off = struct.unpack_from("<I", data, pset_off + 4 + pj * 4)[0]
            ptype_idx, pp = read_uleb128(data, pitem_off + 1)
            pelem_size, pp = read_uleb128(data, pp)
            print(f"      Annotation: {types[ptype_idx]}")
            for pe in range(pelem_size):
                pname_idx, pp = read_uleb128(data, pp)
                print(f"        elem: {strings[pname_idx]}")
