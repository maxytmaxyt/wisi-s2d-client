import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path) as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk")) as apk:
        data = apk.read("classes2.dex")

for target in [b"SCHWAIGER_GERMANY", b"WISI_AUSTRIA", b"WISI_SPAIN"]:
    pos = 0
    while True:
        pos = data.find(target, pos)
        if pos == -1:
            break
        print(f"=== {target.decode()} at {pos} ===")
        print(data[max(0, pos-100):min(len(data), pos+150)])
        pos += len(target)
