import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        for dex in apk.namelist():
            if dex.endswith(".dex"):
                d = apk.read(dex)
                if b"CrenovaDongleInit" in d:
                    print("Found in", dex)
                    for m in re.finditer(rb"[^\x00\"'\s]{0,40}getAboutDongleInfo[^\x00\"'\s]{0,40}", d):
                        print("  ", m.group().decode("latin1", errors="replace"))
