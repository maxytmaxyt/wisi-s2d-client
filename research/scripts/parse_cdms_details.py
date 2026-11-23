import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        data = apk.read("classes2.dex")

# Let's search for all strings around CdmsApi or checkUpdUpdate
idx = 0
while True:
    pos = data.find(b"checkUpdUpdate", idx)
    if pos == -1:
        break
    start = max(0, pos - 200)
    end = min(len(data), pos + 300)
    print("--- Context at", pos, "---")
    print(data[start:end])
    idx = pos + 1
