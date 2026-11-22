import libusb_package
import usb.core
import struct
import sys
import time

sys.path.insert(0, "src")
import protocol
import prepare
from decrypt import descramble_ts_block

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
    payload = raw[:usbs_idx] if usbs_idx != -1 else raw[:expected_len]
    return bytes(payload)

# 1. KeepAlive & Init
usb_send_recv(protocol.cmd_16(), 12, "KeepAlive")
usb_send_recv(protocol.cmd_17_init(), 4, "Init")

# 2. Tune ZDF HD (prog_idx = 1085735055 = 0x40B7008F)
prog_idx = 1085735055
print("Tuning ZDF HD...")
usb_send_recv(protocol.cmd_prepare(prog_idx), 4, "Tune ZDF HD")
time.sleep(0.5)

# 3. Stream Init
usb_send_recv(protocol.cmd_udp_init(), 0, "Stream Init")

# 4. Pull 100 blocks
out_file = "usb_stream_zdf.ts"
total_ts_bytes = 0
block_count = 50

print(f"Pulling {block_count} video blocks over USB-C...")
with open(out_file, "wb") as f:
    for i in range(block_count):
        pull_cmd = protocol.cmd_udp_ts_block(first=(i == 0))
        dev.write(0x02, pull_cmd, timeout=3000)
        
        raw_video = bytearray()
        t0 = time.time()
        while len(raw_video) < protocol.UDP_RESPONSE_SIZE and (time.time() - t0) < 1.0:
            try:
                chunk = dev.read(0x81, protocol.UDP_RESPONSE_SIZE - len(raw_video), timeout=500)
                raw_video.extend(chunk)
            except Exception:
                break
                
        if len(raw_video) >= protocol.UDP_REQUEST_LEN:
            ts_chunk = bytes(raw_video[:protocol.UDP_REQUEST_LEN])
            dec = descramble_ts_block(ts_chunk)
            f.write(dec)
            total_ts_bytes += len(dec)
            if i % 10 == 0:
                print(f"  Block {i}/{block_count} ({total_ts_bytes/1024/1024:.2f} MB)")

print(f"Recorded {total_ts_bytes/1024/1024:.2f} MB to {out_file} over USB-C!")
