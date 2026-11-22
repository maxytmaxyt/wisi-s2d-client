import urllib.request
import urllib.error
import json
import ssl
from concurrent.futures import ThreadPoolExecutor

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_key = "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB"
url = "https://wms.tiviconsolutions.com/api/updater/updates/upd"

buyers = {
    "SCHWAIGER_GERMANY": 7,
    "WISI_AUSTRIA": 24,
    "WISI_SPAIN": 48,
    "WISI_SPAIN_WISION": 220,
    "WISI_6174": 6174
}

def check(cid, name, sw, hw, utype):
    payload = {
        "dongle_sw_version": sw,
        "dongle_hw_type": hw,
        "dongle_customer_id": cid,
        "dongle_chip_id": "9000000035a2a52b",
        "updateType": utype
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": api_key,
        "User-Agent": "okhttp/4.9.0"
    }
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3, context=ctx) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            if d.get("status") != "NO_UPDATE" or d.get("url"):
                print(f"!!! MATCH !!! {name} (CID {cid}) sw={sw} hw={hw} -> {d}")
                return d
    except Exception:
        pass
    return None

tasks = []
with ThreadPoolExecutor(max_workers=15) as ex:
    for name, cid in buyers.items():
        for sw in ["0", "1", "256"]:
            for hw in ["0", "26", "OR S2D", "TC711"]:
                for utype in ["release", "debug"]:
                    tasks.append(ex.submit(check, cid, name, sw, hw, utype))

for t in tasks:
    t.result()

print("Fast check completed.")
