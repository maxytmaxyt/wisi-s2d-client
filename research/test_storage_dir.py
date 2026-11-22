import urllib.request
import urllib.error
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

urls = [
    "https://wms.tiviconsolutions.com/storage/uploads/fw_updates/",
    "https://cdms.tiviconsolutions.com/storage/uploads/fw_updates/",
    "https://wms.tiviconsolutions.com/storage/uploads/upd_updates/",
    "https://cdms.tiviconsolutions.com/storage/uploads/upd_updates/",
]

for url in urls:
    req = urllib.request.Request(url, headers={"User-Agent": "okhttp/4.9.0"})
    try:
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            print(f"[OK {resp.getcode()}] {url}")
            print("  Body:", resp.read()[:200])
    except urllib.error.HTTPError as e:
        print(f"[HTTP {e.code}] {url}")
    except Exception as exc:
        print(f"[ERR] {url}: {exc}")
