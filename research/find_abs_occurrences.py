import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path) as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk")) as apk:
        data = apk.read("classes2.dex")

for m in re.finditer(rb"[^\x00\"'\s<>]{0,40}\.abs[^\x00\"'\s<>]{0,40}", data):
    print("Match:", m.group().decode("latin1", errors="replace"))
