import zipfile
import re

xapk_path = r"C:\Users\thiel\Downloads\TV2Smart_3.M20260803.0-rev-a14aeb377_APKPure.xapk"

patterns = [
    rb"[a-zA-Z0-9_\-\.]+\.bin\b",
    rb"[a-zA-Z0-9_\-\.]+\.upd\b",
    rb"[a-zA-Z0-9_\-\.]+\.img\b",
    rb"[a-zA-Z0-9_\-\.]*fw[a-zA-Z0-9_\-\.]*",
    rb"TC711[a-zA-Z0-9_\-\.]*",
    rb"OR[_\-\s]?S2D[a-zA-Z0-9_\-\.]*",
]

with zipfile.ZipFile(xapk_path) as z:
    for apk_name in z.namelist():
        if apk_name.endswith(".apk"):
            with zipfile.ZipFile(z.open(apk_name)) as apk:
                for f in apk.namelist():
                    data = apk.read(f)
                    for p in patterns:
                        for m in re.finditer(p, data, re.IGNORECASE):
                            match_str = m.group().decode("latin1", errors="replace")
                            if len(match_str) > 4 and not match_str.endswith(".class") and not match_str.endswith(".xml"):
                                if any(x in match_str.lower() for x in ["fw", "update", "tc711", "s2d", "wisi", "crenova", "tivicon"]):
                                    print(f"[{apk_name}:{f}] Match: {match_str}")
