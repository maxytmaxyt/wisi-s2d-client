#!/usr/bin/env bash
# ==============================================================================
# setup_raspberry_pi.sh – Automatisches Setup für WISI OR S2D 24/7 Server
# ==============================================================================
set -e

echo "=== [1/4] Installiere Systempakete & Python-Abhängigkeiten ==="
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv git

# Abhängigkeiten installieren
python3 -m pip install --break-system-packages starlette uvicorn cryptography || python3 -m pip install starlette uvicorn cryptography

echo "=== [2/4] Konfiguriere USB-C Netzwerk-Interface (usb0) ==="
# Wenn der Dongle per USB-C angesteckt ist, meldet er sich meist als usb0 / eth1 (RNDIS/CDC)
# Wir stellen sicher, dass das Interface eine statische IP im Dongle-Subnetz bekommt:
cat << 'EOF' | sudo tee /etc/network/interfaces.d/wisi_usb0 > /dev/null
# WISI OR S2D Dongle USB-Interface
allow-hotplug usb0
iface usb0 inet static
    address 192.168.178.10
    netmask 255.255.255.0
EOF

echo "=== [3/4] Richte 24/7 systemd Hintergrund-Dienst ein ==="
SERVICE_FILE="/etc/systemd/system/wisi-server.service"
CURRENT_DIR="$(pwd)"
CURRENT_USER="$(whoami)"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=WISI OR S2D DVB-over-IP 24/7 Web Control Center
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_DIR
ExecStart=/usr/bin/python3 -m wisi.ui --host 0.0.0.0 --port 8888 --no-browser
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wisi-server.service
sudo systemctl restart wisi-server.service

echo "=== [4/4] Fertig! ==="
IP_ADDR=$(hostname -I | awk '{print $1}')
echo ""
echo "===================================================================="
echo " Der WISI OR S2D 24/7 Server läuft jetzt als Hintergrund-Dienst!"
echo " Web-Oberfläche erreichbar unter: http://${IP_ADDR}:8888"
echo " M3U-Senderliste für VLC / TV:    http://${IP_ADDR}:8888/playlist.m3u"
echo " Status prüfen:                   sudo systemctl status wisi-server"
echo " Logs ansehen:                    sudo journalctl -u wisi-server -f"
echo "===================================================================="
