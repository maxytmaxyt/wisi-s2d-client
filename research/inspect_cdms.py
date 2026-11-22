import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

with zipfile.ZipFile(xapk_path, "r") as z:
    for name in z.namelist():
        if name.endswith(".apk"):
            print("Found APK:", name)
            with zipfile.ZipFile(z.open(name), "r") as apk:
                for dex in apk.namelist():
                    if dex.endswith(".dex"):
                        data = apk.read(dex)
                        for match in re.finditer(rb"https?://cdms\.tiviconsolutions\.com[^\x00\"'\s<>]*", data):
                            print(dex, "URL:", match.group().decode("latin1", errors="ignore"))
                        for match in re.finditer(rb"[a-zA-Z0-9_/]*checkUpdUpdate[a-zA-Z0-9_/\$]*", data):
                            print(dex, "checkUpd:", match.group().decode("latin1", errors="ignore"))
                        for match in re.finditer(rb"[a-zA-Z0-9_/]*checkFwUpdate[a-zA-Z0-9_/\$]*", data):
                            print(dex, "checkFw:", match.group().decode("latin1", errors="ignore"))
                        for match in re.finditer(rb"api/operator/[^\x00\"'\s<>]*", data):
                            print(dex, "operator:", match.group().decode("latin1", errors="ignore"))
                        for match in re.finditer(rb"api/dongle/[^\x00\"'\s<>]*", data):
                            print(dex, "dongle_api:", match.group().decode("latin1", errors="ignore"))
