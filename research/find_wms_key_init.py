import zipfile
import struct
import re

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

field_ids_size = struct.unpack_from("<I", data, 0x50)[0]
field_ids_off = struct.unpack_from("<I", data, 0x54)[0]
fields = []
wms_key_fid = None
url_base_fid = None
for i in range(field_ids_size):
    class_idx, type_idx, name_idx = struct.unpack_from("<HHI", data, field_ids_off + i * 8)
    fname = strings[name_idx]
    if fname == "WMS_API_KEY":
        wms_key_fid = i
        print(f"WMS_API_KEY fid={i}")
    elif fname == "URL_BASE":
        url_base_fid = i
        print(f"URL_BASE fid={i}")

# Search for sput-object (0x69) with wms_key_fid or url_base_fid
for fid, name in [(wms_key_fid, "WMS_API_KEY"), (url_base_fid, "URL_BASE")]:
    if fid is None:
        continue
    target = struct.pack("<H", fid)
    for m in re.finditer(re.escape(target), data):
        pos = m.start()
        # check if preceding byte is 0x69 (sput-object)
        if pos >= 2 and data[pos-2] == 0x69:
            print(f"sput-object to {name} at offset {pos-2}")
            # inspect preceding 60 bytes
            sub = data[pos-60:pos]
            for j in range(len(sub)-4):
                if sub[j] == 0x1a:
                    sidx = struct.unpack_from("<H", sub, j+2)[0]
                    if sidx < len(strings):
                        print(f"  const-string: '{strings[sidx]}'")
                elif sub[j] == 0x1b:
                    sidx = struct.unpack_from("<I", sub, j+2)[0]
                    if sidx < len(strings):
                        print(f"  const-string/jumbo: '{strings[sidx]}'")
