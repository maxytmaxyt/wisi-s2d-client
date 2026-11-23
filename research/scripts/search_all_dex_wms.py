import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    with zipfile.ZipFile(z.open("com.tivicon.tv2smart.mobile.apk"), "r") as apk:
        for dex in apk.namelist():
            if dex.endswith(".dex"):
                d = apk.read(dex)
                for m in re.finditer(rb"[^\x00\"'\s]{0,30}WmsURI[^\x00\"'\s]{0,30}", d):
                    print(dex, "WmsURI match:", m.group().decode("latin1", errors="replace"))
                for m in re.finditer(rb"[^\x00\"'\s]{0,30}WMS_API_KEY[^\x00\"'\s]{0,30}", d):
                    print(dex, "WMS_API_KEY match:", m.group().decode("latin1", errors="replace"))
