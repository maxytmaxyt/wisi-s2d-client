import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path) as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk")) as apk:
        data = apk.read("classes2.dex")

matches = set()
for m in re.finditer(rb"(?:SCHWAIGER|WISI|TIVICON|TELESTAR|CRENOVA|MEGASAT|DYON|XORO)[a-zA-Z0-9_]*", data, re.IGNORECASE):
    matches.add(m.group().decode("latin1", errors="replace"))

for m in sorted(matches):
    print(m)
