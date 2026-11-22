import urllib.request
import re
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = "https://schwaiger.de/products/sat-dongle-digitale-fernsehsignale-per-wifi-hdtv-fta-dsrd0100"
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        html = resp.read().decode("utf-8", errors="replace")
        links = re.findall(r'href=[\'"]([^\'"]+)[\'"]', html)
        for l in links:
            if any(ext in l.lower() for ext in [".abs", ".bin", ".zip", ".tar", ".rar", "download"]):
                print("Found download link:", l)
except Exception as e:
    print("Error:", e)
