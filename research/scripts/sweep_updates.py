import urllib.request
import urllib.error
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_keys = {
    "NG6k": "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB",
    "QhC6": "QhC6rpwfYIe7TlMTNDnoArEkWy3vXlGRvjnoGjXiy7RIWBQBwpj4t9yGlPZ8"
}

sw_versions = [
    "0", "1", "10", "100", "0.0.1", "0.1", "v0.1", "0.0.0.0", "1.0.0", "0x0000", "0x0100",
    0, 1, 100, 255
]

hw_types = ["0", "1", "26", "OR S2D", "WISI OR S2D", "TC711", "TC711CXD", 0, 26]
update_types = ["release", "debug"]

url = "https://wms.tiviconsolutions.com/api/updater/updates/upd"

results = []

for sw in sw_versions:
    for hw in ["0", "26", "OR S2D"]:
        for utype in update_types:
            payload = {
                "dongle_sw_version": sw,
                "dongle_hw_type": hw,
                "dongle_customer_id": 6174,
                "dongle_chip_id": "9000000035a2a52b",
                "updateType": utype
            }
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Api-Key": api_keys["NG6k"],
                "User-Agent": "okhttp/4.9.0"
            }
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    if resp_data.get("status") != "NO_UPDATE" or resp_data.get("url"):
                        print(f"!!! FOUND UPDATE !!! sw={sw} hw={hw} utype={utype} -> {resp_data}")
                        results.append((sw, hw, utype, resp_data))
            except Exception as e:
                pass

if not results:
    print("All combinations returned NO_UPDATE.")
