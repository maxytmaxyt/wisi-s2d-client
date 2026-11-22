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

# Strings
string_ids_size = struct.unpack_from("<I", data, 0x38)[0]
string_ids_off = struct.unpack_from("<I", data, 0x3C)[0]
strings = []
for i in range(string_ids_size):
    off = struct.unpack_from("<I", data, string_ids_off + i * 4)[0]
    length, idx = read_uleb128(data, off)
    end = data.find(b"\x00", idx)
    strings.append(data[idx:end].decode("latin1", errors="replace"))

# Types
type_ids_size = struct.unpack_from("<I", data, 0x40)[0]
type_ids_off = struct.unpack_from("<I", data, 0x44)[0]
types = [strings[struct.unpack_from("<I", data, type_ids_off + i * 4)[0]] for i in range(type_ids_size)]

# Methods
method_ids_size = struct.unpack_from("<I", data, 0x58)[0]
method_ids_off = struct.unpack_from("<I", data, 0x5C)[0]
methods = []
for i in range(method_ids_size):
    class_idx, proto_idx, name_idx = struct.unpack_from("<HHI", data, method_ids_off + i * 8)
    methods.append((types[class_idx], strings[name_idx]))

# Let's inspect CdmsApi annotations_off = 8293024
annot_off = 8293024
# annotations_directory_item:
# u4 class_annotations_off
# u4 fields_size
# u4 annotated_methods_size
# u4 annotated_parameters_size
class_annot_off, fields_size, methods_size, params_size = struct.unpack_from("<IIII", data, annot_off)
print(f"CdmsApi annot: class_annot_off={class_annot_off}, fields_size={fields_size}, methods_size={methods_size}, params_size={params_size}")

curr = annot_off + 16
# Next are method_annotation: method_idx (u4), annotations_off (u4)
for i in range(methods_size):
    midx, aoff = struct.unpack_from("<II", data, curr)
    curr += 8
    print(f"Method #{midx}: {methods[midx]} -> annotations_off={aoff}")
    # read annotation_set_item at aoff
    size = struct.unpack_from("<I", data, aoff)[0]
    for j in range(size):
        item_off = struct.unpack_from("<I", data, aoff + 4 + j * 4)[0]
        # annotation_item: visibility (u1), annotation (encoded_annotation)
        vis = data[item_off]
        type_idx, p = read_uleb128(data, item_off + 1)
        print(f"   Annotation type: {types[type_idx]}")
        size_elements, p = read_uleb128(data, p)
        for e in range(size_elements):
            name_idx, p = read_uleb128(data, p)
            # value is encoded_value: (value_arg << 5) | value_type
            v_hdr = data[p]
            p += 1
            v_type = v_hdr & 0x1f
            v_arg = v_hdr >> 5
            print(f"     Element: {strings[name_idx]} (type={v_type}, arg={v_arg})")
            if v_type == 0x17: # string
                # size is v_arg + 1
                str_idx = 0
                for b_i in range(v_arg + 1):
                    str_idx |= data[p] << (b_i * 8)
                    p += 1
                print(f"       Value string: {strings[str_idx]}")

# Parameter annotations: method_idx (u4), annotations_off (u4)
for i in range(params_size):
    midx, aoff = struct.unpack_from("<II", data, curr)
    curr += 8
    print(f"Param Annot Method #{midx}: {methods[midx]} -> annotations_off={aoff}")
    # annotation_set_ref_list: size (u4), list of annotation_set_item off
    pref_size = struct.unpack_from("<I", data, aoff)[0]
    for pidx in range(pref_size):
        pset_off = struct.unpack_from("<I", data, aoff + 4 + pidx * 4)[0]
        if pset_off == 0:
            continue
        psize = struct.unpack_from("<I", data, pset_off)[0]
        for pj in range(psize):
            pitem_off = struct.unpack_from("<I", data, pset_off + 4 + pj * 4)[0]
            ptype_idx, pp = read_uleb128(data, pitem_off + 1)
            pelem_size, pp = read_uleb128(data, pp)
            for pe in range(pelem_size):
                pname_idx, pp = read_uleb128(data, pp)
                pv_hdr = data[pp]
                pp += 1
                pv_type = pv_hdr & 0x1f
                pv_arg = pv_hdr >> 5
                val_str = ""
                if pv_type == 0x17:
                    s_idx = 0
                    for b_i in range(pv_arg + 1):
                        s_idx |= data[pp] << (b_i * 8)
                        pp += 1
                    val_str = strings[s_idx]
                print(f"     Param {pidx} annot: {types[ptype_idx]} {strings[pname_idx]}='{val_str}'")
