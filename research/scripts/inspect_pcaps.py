import zipfile
import struct
import io
import re

pcap_zip = r"C:\Users\thiel\Downloads\wisi-s2d-client-main (1).zip"

with zipfile.ZipFile(pcap_zip) as z:
    for name in z.namelist():
        if name.endswith(".pcap"):
            print("=== PCAP:", name, "===")
            pcap_data = z.read(name)
            # Find HTTP requests or hostnames in pcap
            urls = set(re.findall(rb"GET [^\r\n]+", pcap_data))
            posts = set(re.findall(rb"POST [^\r\n]+", pcap_data))
            hosts = set(re.findall(rb"Host: [^\r\n]+", pcap_data))
            print("  Hosts:", [h.decode('latin1', errors='replace') for h in hosts][:10])
            print("  GETs:", [u.decode('latin1', errors='replace') for u in urls][:10])
            print("  POSTs:", [p.decode('latin1', errors='replace') for p in posts][:10])
            # search for .abs, update, tivicon
            for match in re.finditer(rb"[a-zA-Z0-9_\-\./]+\.abs", pcap_data):
                print("  ABS match:", match.group().decode('latin1', errors='replace'))
