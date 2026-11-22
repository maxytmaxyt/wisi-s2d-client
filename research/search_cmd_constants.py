import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path) as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk")) as apk:
        data = apk.read("classes2.dex")

# In DEX, bytes 0xFA in opcode tables or constants
matches = set()
for m in re.finditer(rb"(?:CMD_|ACTION_|MSG_)[a-zA-Z0-9_]+", data):
    s = m.group().decode("latin1", errors="replace")
    if any(x in s for x in ["UPDATE", "UPGRADE", "FLASH", "READ", "DONGLE", "BOOT", "DUMP", "FIRMWARE"]):
        matches.add(s)

for m in sorted(matches):
    print(m)
