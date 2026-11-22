import urllib.request
import urllib.error
import json
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_keys = [
    "NG6kM6XVM8YAQWHq2DRXsA2fNntMDdE64SgAy41KmfZXYlkQzAJwivR6K9PB",
    "QhC6rpwfYIe7TlMTNDnoArEkWy3vXlGRvjnoGjXiy7RIWBQBwpj4t9yGlPZ8",
    ""
]

urls = [
    "https://cdms.tiviconsolutions.com/api/updater/updates/upd",
    "https://wms.tiviconsolutions.com/api/updater/updates/upd",
    "https://cdms.tiviconsolutions.com/api/operator/updater/updates/upd",
]

payloads = [
    {
        "dongle_sw_version": "256",
        "dongle_hw_type": "0",
        "dongle_customer_id": 6174,
        "dongle_chip_id": "9000000035a2a52b",
        "updateType": "release"
    },
    {
        "dongle_sw_version": "1.0",
        "dongle_hw_type": "OR S2D",
        "dongle_customer_id": 6174,
        "dongle_chip_id": "9000000035a2a52b",
        "updateType": "release"
    },
    {
        "dongle_sw_version": "v1.0",
        "dongle_hw_type": "26",
        "dongle_customer_id": 6174,
        "dongle_chip_id": "9000000035a2a52b",
        "updateType": "release"
    }
]

for url in urls:
    for key in api_keys:
        for p_idx, payload in enumerate(payloads):
            data = json.dumps(payload).encode("utf-8")
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "okhttp/4.9.0",
            }
            if key:
                headers["X-Api-Key"] = key
            
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
                    code = resp.getcode()
                    body = resp.read().decode("utf-8", errors="replace")
                    print(f"[SUCCESS {code}] url={url} key={key[:8]}... p={p_idx} -> {body}")
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                print(f"[HTTP {e.code}] url={url} key={key[:8]}... p={p_idx} -> {err_body[:100]}")
            except Exception as exc:
                print(f"[ERR] url={url} key={key[:8]}... -> {exc}")
