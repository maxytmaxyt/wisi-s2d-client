import socket
import struct
import sys
sys.path.insert(0, "src")
import protocol

ip = "192.168.178.32"
print(f"Connecting to {ip}:8802...")
sock = protocol.connect(ip)
if not sock:
    print("Failed to connect.")
    sys.exit(1)

def test_read_cmd(prefix, opcode, length, name):
    cmd = protocol.build_usbc(length, 0x80, prefix, opcode)
    try:
        resp = protocol.send_recv(sock, cmd, length, name, recv_timeout=2.0)
        print(f"[{name}] (len={len(resp)}): {resp.hex()}")
        # print ascii if printable
        ascii_repr = "".join(chr(b) if 32 <= b <= 126 else "." for b in resp)
        print(f"  ASCII: {ascii_repr}")
        return resp
    except Exception as e:
        print(f"[{name}] Error: {e}")
        return None

test_read_cmd(0xFA, 0x01, 6, "0xFA/0x01 (6B)")
test_read_cmd(0xFA, 0x0B, 4, "0xFA/0x0B (4B)")
test_read_cmd(0xFA, 0x0D, 8, "0xFA/0x0D (8B)")
test_read_cmd(0xFA, 0x12, 52, "0xFA/0x12 (52B)")
test_read_cmd(0xFA, 0x14, 24, "0xFA/0x14 (24B)")

protocol.disconnect(sock)
print("Disconnected.")
