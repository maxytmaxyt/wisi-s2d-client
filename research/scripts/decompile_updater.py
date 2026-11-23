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
    fields.append((types[class_idx], strings[name_idx], types[type_idx]))

class_defs_size = struct.unpack_from("<I", data, 0x60)[0]
class_defs_off = struct.unpack_from("<I", data, 0x64)[0]

target_classes = [
    "Lcom/android/tv/crenova/ui/updater/OnLineDongleInfo;",
    "Lcom/android/tv/crenova/ui/updater/OnLineDongleInfoDev;",
    "Lcom/android/tv/crenova/ui/updater/OnLineDongleInfo$1;",
    "Lcom/crenova/tv/dongle/dvb/sdk/ui/updater/OnLineDongleInfo;"
]

for i in range(class_defs_size):
    off = class_defs_off + i * 32
    class_idx, access_flags, superclass_idx, interfaces_off, source_file_idx, annotations_off, class_data_off, static_values_off = struct.unpack_from("<IIIIIIII", data, off)
    cname = types[class_idx]
    if cname in target_classes:
        print(f"\n==========================================")
        print(f"CLASS: {cname}")
        p = class_data_off
        static_fields_size, p = read_uleb128(data, p)
        instance_fields_size, p = read_uleb128(data, p)
        direct_methods_size, p = read_uleb128(data, p)
        virtual_methods_size, p = read_uleb128(data, p)
        print(f"  Fields: {static_fields_size} static, {instance_fields_size} instance")
        print(f"  Methods: {direct_methods_size} direct, {virtual_methods_size} virtual")
        
        # skip fields
        for _ in range(static_fields_size + instance_fields_size):
            _, p = read_uleb128(data, p)
            _, p = read_uleb128(data, p)
            
        mid = 0
        for _ in range(direct_methods_size + virtual_methods_size):
            mid_diff, p = read_uleb128(data, p)
            mid += mid_diff
            acc, p = read_uleb128(data, p)
            code_off, p = read_uleb128(data, p)
            m_class, m_name = methods[mid]
            print(f"\n  METHOD: {m_name} (code_off={code_off})")
            if code_off != 0:
                insns_size = struct.unpack_from("<I", data, code_off + 12)[0]
                insns = data[code_off + 16 : code_off + 16 + insns_size * 2]
                # Let's inspect instructions in insns: strings, method calls, etc.
                ip = 0
                while ip < len(insns):
                    op = insns[ip]
                    if op == 0x1a: # const-string
                        sidx = struct.unpack_from("<H", insns, ip + 2)[0]
                        print(f"    const-string: '{strings[sidx]}'")
                        ip += 4
                    elif op == 0x1b: # const-string/jumbo
                        sidx = struct.unpack_from("<I", insns, ip + 2)[0]
                        print(f"    const-string/jumbo: '{strings[sidx]}'")
                        ip += 6
                    elif op in (0x6e, 0x6f, 0x70, 0x71, 0x72): # invoke-kind
                        target_mid = struct.unpack_from("<H", insns, ip + 2)[0]
                        print(f"    invoke: {methods[target_mid]}")
                        ip += 6
                    elif op in (0x74, 0x75, 0x76, 0x77, 0x78): # invoke-kind/range
                        target_mid = struct.unpack_from("<H", insns, ip + 2)[0]
                        print(f"    invoke/range: {methods[target_mid]}")
                        ip += 6
                    elif op in (0x52, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58): # iget
                        target_fid = struct.unpack_from("<H", insns, ip + 2)[0]
                        print(f"    iget: {fields[target_fid]}")
                        ip += 4
                    elif op in (0x60, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66): # sget
                        target_fid = struct.unpack_from("<H", insns, ip + 2)[0]
                        print(f"    sget: {fields[target_fid]}")
                        ip += 4
                    else:
                        ip += 2
