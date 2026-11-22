import urllib.request
import urllib.error
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_key = "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB"

base_url = "https://wms.tiviconsolutions.com/api/"

dongle_data = {
    "dongle_sw_version": "256",
    "dongle_hw_type": "0",
    "dongle_customer_id": 6174,
    "dongle_chip_id": "9000000035a2a52b",
    "chip_id": "9000000035a2a52b",
    "serial_number": "84fd3834ea66",
    "mac_address": "00:25:ff:01:01:03",
    "model_name": "OR S2D",
    "updateType": "release"
}

endpoints = [
    ("POST", "dongles/check-dongle"),
    ("POST", "dongles/listen"),
    ("POST", "dongles/register"),
    ("POST", "updater/updates/upd"),
    ("POST", "binary-channel-list/cha"),
    ("GET", "channel-manager/version"),
    ("GET", "bouquets/version"),
]

for method, ep in endpoints:
    url = base_url + ep
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Api-Key": api_key,
        "User-Agent": "okhttp/4.9.0",
    }
    data = json.dumps(dongle_data).encode("utf-8") if method == "POST" else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[OK {resp.getcode()}] {ep}: {body[:200]}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTP {e.code}] {ep}: {body[:200]}")
    except Exception as exc:
        print(f"[ERR] {ep}: {exc}")
