"""
detect_dongle.py – Diagnose-Werkzeug für USB- und Netzwerk-Erkennung des WISI OR S2D
"""
from __future__ import annotations

import socket
import sys
import time

def check_tcp_port(ip: str, port: int = 8802, timeout: float = 1.5) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False

def main() -> None:
    print("=" * 64)
    print("  WISI OR S2D – Dongle-Erkennung & Schnittstellen-Prüfung")
    print("=" * 64)

    test_ips = ["192.168.178.32", "192.168.178.1", "10.20.0.1", "192.168.2.80"]
    print("\n[1] Prüfe Standard-IPs auf TCP Port 8802 (Steuerkanal)...")
    found = False
    for ip in test_ips:
        ok = check_tcp_port(ip)
        print(f"  - {ip:16s} : {'✅ ERREICHBAR (Port 8802 OFFEN!)' if ok else '❌ Nicht erreichbar'}")
        if ok:
            found = True

    if not found:
        print("\n[2] Führe UDP Broadcast-Discovery auf Port 8802 durch...")
        try:
            from pathlib import Path
            src_dir = str(Path(__file__).resolve().parents[1] / "src")
            if src_dir not in sys.path:
                sys.path.insert(0, src_dir)
            from wisi_s2d.cli import discovery
            seq_id = int(time.time()) & 0xFFFFFFFF
            req = discovery.build_request(seq_id)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                udp.settimeout(1.5)
                udp.sendto(req, ("255.255.255.255", 8802))
                deadline = time.monotonic() + 1.5
                while time.monotonic() < deadline:
                    try:
                        data, addr = udp.recvfrom(2048)
                        parsed = discovery.parse_response(data)
                        if parsed:
                            print(f"  ✅ Gefunden via UDP Broadcast: {addr[0]} ({parsed.get('model_name', 'WISI OR S2D')})")
                            found = True
                    except TimeoutError:
                        break
        except Exception as e:
            print(f"  Broadcast-Suche Fehler: {e}")

    print("\nErgebnis:")
    if found:
        print("  🎉 Dongle wurde erfolgreich erkannt!")
        print("  Du kannst den Server starten mit: python start_ui.py  (oder: wisi-ui)")
    else:
        print("  ℹ️ Kein Dongle gefunden. Stelle sicher, dass:")
        print("     1. Der Dongle mit 12V Netzteil versorgt ist (rote/blaue LED leuchtet).")
        print("     2. Das USB-C Datenkabel mit dem PC / Raspberry Pi verbunden ist.")
        print("     3. Die Netzwerkkarte (RNDIS/USB) aktiviert ist.")
    print("=" * 64)

if __name__ == "__main__":
    main()
