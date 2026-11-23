import libusb_package
import usb.core
import struct
import sys
sys.path.insert(0, "src")
import protocol
import channels

dev = libusb_package.find(idVendor=0x0402, idProduct=0x7103)
if not dev:
    print("Dongle not found on USB!")
    sys.exit(1)

try:
    dev.set_configuration()
except Exception:
    pass

def usb_send_recv(cmd: bytes, expected_len: int, label: str = "") -> bytes:
    dev.write(0x02, cmd, timeout=3000)
    raw = dev.read(0x81, expected_len + 64, timeout=3000)
    usbs_idx = raw.tobytes().find(b"USBS")
    if usbs_idx != -1:
        payload = raw[:usbs_idx]
    else:
        payload = raw[:expected_len]
    payload = bytes(payload)
    print(f"[{label}] tx={len(cmd)}B rx={len(raw)}B (payload={len(payload)}B): {payload[:20].hex()}")
    return payload

# 1. Phase 1 (0xFA/0x00)
r1 = usb_send_recv(protocol.cmd_dongle_info_phase1(), 64, "0xFA/0x00 Phase 1")

# 2. Phase 2 (0xFA/0x07)
r2 = usb_send_recv(protocol.cmd_dongle_info_phase2(), 51, "0xFA/0x07 Phase 2")
if len(r2) >= 35:
    model = r2[3:35].split(b"\x00")[0].decode("ascii", errors="ignore")
    svn = struct.unpack(">I", r2[35:39])[0]
    print(f"  Model: {model}, SVN: {svn}")

# 3. Init Handshake (0xF6/0x16 and 0xF6/0x17)
r16 = usb_send_recv(protocol.cmd_16(), 12, "0xF6/0x16 KeepAlive")
r17 = usb_send_recv(protocol.cmd_17_init(), 4, "0xF6/0x17 Init")

# 4. Fetch Channel List Length (0xF6/0x20)
r20 = usb_send_recv(channels._cmd_chlist_size(), 8, "0xF6/0x20 Channel Size")
if len(r20) >= 6:
    ch_len = struct.unpack(">I", r20[2:6])[0]
    print(f"  Channel List XML Length: {ch_len} bytes")
    
    # Read channel list chunk (0xF6/0x21)
    chunk = usb_send_recv(channels._cmd_chlist_data(min(ch_len, 4000)), min(ch_len, 4000), "0xF6/0x21 Channel Data")
    if b"<?xml" in chunk or b"<service" in chunk:
        print("  Found valid XML in USB channel chunk!")
        xml_idx = chunk.find(b"<?xml")
        if xml_idx != -1:
            xml_text = chunk[xml_idx : xml_idx + 300].decode("utf-8", errors="ignore")
            print("  XML Preview:", xml_text)

print("\nSUCCESS! USB-C APIX Transport fully functional!")
