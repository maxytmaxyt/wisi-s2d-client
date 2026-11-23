import zipfile
import struct

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        data = apk.read("classes2.dex")

def get_dex_tables(dex_bytes):
    def read_uleb128(idx):
        val = 0
        shift = 0
        while True:
            b = dex_bytes[idx]
            idx += 1
            val |= (b & 0x7f) << shift
            if not (b & 0x80):
                break
            shift += 7
        return val, idx

    string_ids_size = struct.unpack_from("<I", dex_bytes, 0x38)[0]
    string_ids_off = struct.unpack_from("<I", dex_bytes, 0x3C)[0]
    strings = []
    for i in range(string_ids_size):
        off = struct.unpack_from("<I", dex_bytes, string_ids_off + i * 4)[0]
        length, idx = read_uleb128(off)
        end = dex_bytes.find(b"\x00", idx)
        strings.append(dex_bytes[idx:end].decode("latin1", errors="replace"))

    type_ids_size = struct.unpack_from("<I", dex_bytes, 0x40)[0]
    type_ids_off = struct.unpack_from("<I", dex_bytes, 0x44)[0]
    types = [strings[struct.unpack_from("<I", dex_bytes, type_ids_off + i * 4)[0]] for i in range(type_ids_size)]

    method_ids_size = struct.unpack_from("<I", dex_bytes, 0x58)[0]
    method_ids_off = struct.unpack_from("<I", dex_bytes, 0x5C)[0]
    methods = []
    for i in range(method_ids_size):
        class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", dex_bytes, method_ids_off + i * 8)
        methods.append((types[class_idx], strings[name_idx]))

    class_defs_size = struct.unpack_from("<I", dex_bytes, 0x60)[0]
    class_defs_off = struct.unpack_from("<I", dex_bytes, 0x64)[0]

    return strings, types, methods, class_defs_size, class_defs_off, read_uleb128

strings, types, methods, class_defs_size, class_defs_off, read_uleb128 = get_dex_tables(data)

print(f"Loaded {len(strings)} strings, {len(types)} types, {len(methods)} methods, {class_defs_size} classes")

# Search for classes containing CdmsApi or OnLineDongleInfo
for i in range(class_defs_size):
    off = class_defs_off + i * 32
    class_idx, access_flags, superclass_idx, interfaces_off, source_file_idx, annotations_off, class_data_off, static_values_off = struct.unpack_from("<IIIIIIII", data, off)
    cname = types[class_idx]
    if "CdmsApi" in cname or "OnLineDongleInfo" in cname or "UpdateDataModel" in cname:
        print(f"\nClass: {cname} (annotations_off={annotations_off}, class_data_off={class_data_off})")
        # Let's inspect annotations if present
        if annotations_off != 0:
            print(f"  Annotations at {annotations_off}")
            # print raw bytes of annotations
            print("  Raw annot:", data[annotations_off:annotations_off+100].hex())
