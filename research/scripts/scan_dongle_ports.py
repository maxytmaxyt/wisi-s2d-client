import socket

target_ip = "192.168.178.32"
ports = [21, 22, 23, 53, 80, 443, 554, 1900, 8000, 8080, 8800, 8801, 8802, 8803, 8888, 9000, 2323, 5555]

print(f"Scanning common ports on {target_ip}...")
open_ports = []
for port in ports:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        res = s.connect_ex((target_ip, port))
        if res == 0:
            print(f"Port {port} TCP is OPEN!")
            open_ports.append(port)
    except Exception as e:
        pass
    finally:
        s.close()

print(f"Open TCP ports: {open_ports}")
