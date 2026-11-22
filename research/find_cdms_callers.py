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

# Method 27590 is checkUpdUpdate. In Dalvik bytecode, invoke-interface is 0x72 or invoke-virtual is 0x6e
# Let's search for opcode followed by method index 27590 (0x6bc6 in little-endian: c6 6b)
target_method_bytes = struct.pack("<H", 27590)
print(f"Searching for invocations of method 27590 (bytes: {target_method_bytes.hex()})")

matches = [m.start() for m in re.finditer(re.escape(target_method_bytes), data)]
print(f"Found {len(matches)} occurrences in classes2.dex")

for pos in matches:
    # check if opcode at pos - 2 or pos - 1 is an invoke opcode (0x6e..0x72)
    # invoke-kind: opcode is 1 byte, but in 16-bit word: [opcode, B|A] or similar
    # In dex, invoke-interface is 0x72: byte 0 is 0x72, byte 1 is {count | reg}, bytes 2-3 is method_idx
    if pos >= 2 and data[pos - 2] in (0x6e, 0x6f, 0x70, 0x71, 0x72, 0x74, 0x75, 0x76, 0x77, 0x78):
        print(f"Match at offset {pos-2}: opcode=0x{data[pos-2]:02x}")
        # Let's look at the surrounding 200 bytes before this invoke to see the HashMap puts!
        start = max(0, pos - 300)
        end = min(len(data), pos + 100)
        code_chunk = data[start:end]
        print(f"  Surrounding bytecode slice len={len(code_chunk)}")
        # Look for const-string instructions in this chunk: 0x1a (const-string) or 0x1b (const-string/jumbo)
        # 0x1a: [1a, reg, string_idx_low, string_idx_high]
        for cpos in range(len(code_chunk) - 4):
            if code_chunk[cpos] == 0x1a:
                sidx = struct.unpack_from("<H", code_chunk, cpos + 2)[0]
                if sidx < len(strings):
                    print(f"    const-string: '{strings[sidx]}'")
            elif code_chunk[cpos] == 0x1b:
                sidx = struct.unpack_from("<I", code_chunk, cpos + 2)[0]
                if sidx < len(strings):
                    print(f"    const-string/jumbo: '{strings[sidx]}'")
