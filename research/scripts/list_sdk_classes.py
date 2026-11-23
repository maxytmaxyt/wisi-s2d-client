import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        data = apk.read("classes2.dex")

matches = set()
for m in re.finditer(rb"Lcom/crenova/tv/dongle/dvb/sdk/[a-zA-Z0-9_\$]+;", data):
    matches.add(m.group().decode("latin1"))

for c in sorted(matches):
    print(c)
