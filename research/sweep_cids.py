import urllib.request
import urllib.error
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_key = "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB"
url = "https://wms.tiviconsolutions.com/api/updater/updates/upd"

cids = [
    203, 224, 141, 164, 159, 114, 157, 34, 120, 163, 33, 122, 130, 74, 131, 116, 106, 155, 133, 128, 129,
    187, 30, 149, 225, 152, 115, 199, 118, 4, 170, 179, 96, 178, 113, 219, 119, 132, 123, 156, 127, 82,
    153, 177, 139, 0, 110, 191, 212, 126, 184, 202, 135, 241, 45, 80, 124, 7, 154, 204, 186, 109, 62, 121,
    176, 125, 162, 151, 136, 209, 227, 137, 117, 201, 134, 198, 210, 183, 24, 48, 220, 161, 214, 6174
]

for cid in cids:
    payload = {
        "dongle_sw_version": "0.1",
        "dongle_hw_type": "0",
        "dongle_customer_id": cid,
        "dongle_chip_id": "9000000035a2a52b",
        "updateType": "release"
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
                print(f"!!! MATCH FOR CID {cid} !!! -> {d}")
    except Exception as e:
        pass
print("Finished checking CIDs.")
