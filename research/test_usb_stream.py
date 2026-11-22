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
    print(f"[{label}] tx={len(cmd)}B rx={len(raw)}B (payload={len(payload)}B): {bytes(payload)[:16].hex()}")
    return bytes(payload)

# 1. KeepAlive & Init
usb_send_recv(protocol.cmd_16(), 12, "KeepAlive")
usb_send_recv(protocol.cmd_17_init(), 4, "Init")

# 2. Tune ZDF HD (prog_idx = 1085735055 = 0x40B7008F)
prog_idx = 1085735055
print(f"\n--- Tuning ZDF HD (0x{prog_idx:08X}) over USB-C ---")
usb_send_recv(protocol.cmd_prepare(prog_idx), 4, "Tune ZDF HD")
time.sleep(0.5)

# 3. Check Signal
sig = usb_send_recv(protocol.cmd_signal(), 17, "Signal Check")
if len(sig) >= 5:
    lock = "LOCK" if (sig[2] & 0x01) else "NO LOCK"
    print(f"Signal: {lock}, Strength={sig[3]}%, Quality={sig[4]}%")

# 4. Stream Init (0xF9/0x02)
print("\n--- Initializing Video Stream (0xF9/0x02) over USB-C ---")
usb_send_recv(protocol.cmd_udp_init(), 0, "Stream Init 0xF9/0x02")

# 5. Pull MPEG-TS Video Block (0xF9/0x01)
print("\n--- Pulling MPEG-TS Video Block 1 (0xF9/0x01) over USB-C ---")
pull_cmd = protocol.cmd_udp_ts_block(first=True)
dev.write(0x02, pull_cmd, timeout=3000)

# The video block is 48128 bytes TS + 64 bytes EXTRACSW + 13 bytes USBS = 48205 bytes
raw_video = bytearray()
start = time.time()
while len(raw_video) < protocol.UDP_RESPONSE_SIZE and (time.time() - start) < 3.0:
    try:
        chunk = dev.read(0x81, protocol.UDP_RESPONSE_SIZE - len(raw_video), timeout=1000)
        raw_video.extend(chunk)
    except Exception as e:
        print("Read chunk error/timeout:", e)
        break

print(f"Total Video Bytes Read: {len(raw_video)} bytes!")
if len(raw_video) >= protocol.UDP_REQUEST_LEN:
    ts_data = bytes(raw_video[:protocol.UDP_REQUEST_LEN])
    print("TS Data (first 32B):", ts_data[:32].hex())
    print("Sync byte 0:", hex(ts_data[0]))
    print("Sync byte 188:", hex(ts_data[188]))
    
    # Decrypt
    decrypted = descramble_ts_block(ts_data)
    print("Decrypted TS Sync:", hex(decrypted[0]))
    with open("usb_sample_zdf.ts", "wb") as f:
        f.write(decrypted)
    print("SUCCESS: Saved decrypted video sample to usb_sample_zdf.ts!")
