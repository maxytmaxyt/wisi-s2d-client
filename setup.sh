#!/usr/bin/env bash
# ==============================================================================
# setup.sh – Vollautomatisches Setup für WISI OR S2D auf Dell Mini-PC / Linux
#            (Debian 12/13, Ubuntu, Raspberry Pi OS)
#
# Richtet ein:
#   1. Systempakete (Python, venv, FFmpeg, NetworkManager, dnsmasq-base)
#   2. Isolierte Python-Umgebung (.venv) + wisi-s2d-client
#   3. Netzwerk:
#        - WLAN-Verbindung zum Heimnetz / Router
#        - LAN-Direktverbindung zum WISI-Dongle mit eigenem DHCP-Server (10.42.0.1/24)
#   4. 24/7 systemd-Hintergrunddienst (wisi-server.service) mit --auto-connect
# ==============================================================================
set -euo pipefail

WIFI_SSID=""
WIFI_PASS=""
LAN_IF=""
WIFI_IF=""
SKIP_NETWORK=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --wifi-ssid) WIFI_SSID="${2:-}"; shift 2 ;;
        --wifi-pass) WIFI_PASS="${2:-}"; shift 2 ;;
        --lan-if)    LAN_IF="${2:-}"; shift 2 ;;
        --wifi-if)   WIFI_IF="${2:-}"; shift 2 ;;
        --no-network) SKIP_NETWORK=1; shift ;;
        -h|--help)
            echo "Verwendung: ./setup.sh [Optionen]"
            echo "  --wifi-ssid NAME   WLAN-Name (optional, sonst interaktiv)"
            echo "  --wifi-pass PASS   WLAN-Passwort (optional, sonst interaktiv)"
            echo "  --lan-if IFACE     Ethernet-Schnittstelle für Dongle (z. B. enp1s0)"
            echo "  --wifi-if IFACE    WLAN-Schnittstelle (z. B. wlp2s0)"
            echo "  --no-network       Netzwerkkonfiguration überspringen"
            exit 0
            ;;
        *)
            echo "Unbekannte Option: $1" >&2
            exit 1
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
CURRENT_USER="$(whoami)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "===================================================================="
echo "  WISI OR S2D – Mini-PC 24/7 Setup & Direktverbindung"
echo "===================================================================="
echo "Projektordner: $SCRIPT_DIR"
echo "Benutzer:      $CURRENT_USER"
echo ""

echo "=== [1/4] Installiere Systempakete & FFmpeg (inkl. Intel VA-API) ==="
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git ffmpeg \
    i965-va-driver network-manager dnsmasq-base iproute2
sudo apt-get clean

# GPU-Zugriff (/dev/dri/renderD128) für Hardware-Transkodierung freischalten
for grp in render video; do
    if getent group "$grp" >/dev/null 2>&1; then
        sudo usermod -aG "$grp" "$CURRENT_USER" || true
    fi
done

# Hinweis: Falls früher das volle 'dnsmasq'-Paket installiert wurde,
# blockiert es Port 67 für NetworkManager-Shared-DHCP:
if systemctl is-active --quiet dnsmasq 2>/dev/null; then
    echo "Deaktiviere globales dnsmasq-Paket, damit NetworkManager DHCP auf LAN verwalten kann..."
    sudo systemctl disable --now dnsmasq || true
fi

echo ""
echo "=== [2/4] Richte Python-Umgebung (.venv) ein ==="
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --no-cache-dir --upgrade pip
"$VENV_DIR/bin/pip" install --no-cache-dir -e "$SCRIPT_DIR"

echo ""
if [ "$SKIP_NETWORK" -eq 0 ]; then
    echo "=== [3/4] Richte Netzwerk ein (WLAN Heimnetz + LAN Direkt zum Dongle) ==="
    sudo systemctl enable --now NetworkManager

    # Falls Debian netinst Schnittstellen in /etc/network/interfaces fest verdrahtet hat,
    # übernimmt NetworkManager sie erst nach Bereinigung.
    if [ -f /etc/network/interfaces ] && grep -Eq '^\s*(iface|auto|allow-hotplug)\s+(eth|en|wl)' /etc/network/interfaces; then
        echo ""
        echo "Hinweis: /etc/network/interfaces enthält manuelle Schnittstellen (typisch bei Debian-Server-Installation)."
        echo "Damit NetworkManager WLAN & LAN-DHCP verwalten kann, sollten diese dort entfernt werden."
        read -r -p "Backup anlegen (/etc/network/interfaces.bak) und an NetworkManager übergeben? [J/n] " MIGRATE_IF
        if [[ ! "$MIGRATE_IF" =~ ^[Nn]$ ]]; then
            sudo cp /etc/network/interfaces /etc/network/interfaces.bak
            sudo tee /etc/network/interfaces > /dev/null << 'EOF'
# Verwaltet durch NetworkManager (Backup unter /etc/network/interfaces.bak)
source /etc/network/interfaces.d/*

auto lo
iface lo inet loopback
EOF
            if [ -f /etc/NetworkManager/NetworkManager.conf ]; then
                sudo sed -i 's/managed=false/managed=true/g' /etc/NetworkManager/NetworkManager.conf || true
            fi
            sudo systemctl restart NetworkManager
            sleep 2
        fi
    fi

    # --- WLAN zum Heimnetz/Router ---
    if [ -z "$WIFI_IF" ]; then
        WIFI_IF="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="wifi"{print $1; exit}' || true)"
    fi

    if [ -n "$WIFI_IF" ]; then
        CUR_WIFI="$(nmcli -t -f DEVICE,STATE,CONNECTION device 2>/dev/null | awk -F: -v dev="$WIFI_IF" '$1==dev && $2=="connected"{print $3; exit}' || true)"
        CONFIGURE_WIFI=1
        if [ -n "$CUR_WIFI" ] && [ -z "$WIFI_SSID" ]; then
            echo "WLAN ($WIFI_IF) ist bereits verbunden mit: $CUR_WIFI"
            read -r -p "WLAN neu einrichten oder ändern? [j/N] " CHANGE_WIFI
            if [[ ! "$CHANGE_WIFI" =~ ^[JjYy]$ ]]; then
                CONFIGURE_WIFI=0
            fi
        fi

        if [ "$CONFIGURE_WIFI" -eq 1 ]; then
            if [ -z "$WIFI_SSID" ]; then
                echo "Suche verfügbare WLAN-Netze auf $WIFI_IF..."
                nmcli device wifi rescan ifname "$WIFI_IF" 2>/dev/null || true
                sleep 2
                nmcli -f IN-USE,SSID,SIGNAL,SECURITY device wifi list ifname "$WIFI_IF" || true
                echo ""
                read -r -p "WLAN-Name (SSID, leer lassen zum Überspringen): " WIFI_SSID
            fi
            if [ -n "$WIFI_SSID" ]; then
                if [ -z "$WIFI_PASS" ]; then
                    read -r -s -p "WLAN-Passwort für '$WIFI_SSID': " WIFI_PASS
                    echo ""
                fi
                echo "Verbinde $WIFI_IF mit '$WIFI_SSID'..."
                sudo nmcli device wifi connect "$WIFI_SSID" password "$WIFI_PASS" ifname "$WIFI_IF"
                sudo nmcli connection modify "$WIFI_SSID" connection.autoconnect yes 2>/dev/null || true
            fi
        fi
    else
        echo "Hinweis: Keine WLAN-Schnittstelle gefunden (beim Wyse 3040 ggf. USB-WLAN-Stick oder zweiten USB-LAN-Adapter verwenden)."
    fi

    # --- LAN Direktverbindung zum WISI Dongle (DHCP-Server im 10.42.0.0/24 Subnetz) ---
    ETH_COUNT="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="ethernet"{c++} END{print c+0}')"
    if [ -z "$LAN_IF" ]; then
        # Falls 2 Ethernet-Ports vorhanden (z. B. intern + USB-LAN), zweiten Port vorschlagen
        if [ "$ETH_COUNT" -ge 2 ]; then
            LAN_IF="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="ethernet"{print $1}' | tail -n1 || true)"
        else
            LAN_IF="$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | awk -F: '$2=="ethernet"{print $1; exit}' || true)"
        fi
    fi

    CONFIGURE_LAN=1
    if [ -z "$WIFI_IF" ] && [ "$ETH_COUNT" -le 1 ] && [ -n "$LAN_IF" ]; then
        echo ""
        echo "ACHTUNG: Es ist weder WLAN noch ein zweiter LAN-Adapter erkannt worden!"
        echo "Wenn du '$LAN_IF' jetzt auf die Direktverbindung zum Dongle (10.42.0.1/24) umstellst,"
        echo "ist der Mini-PC danach nicht mehr über das Heimnetz erreichbar (SSH bricht ab)."
        read -r -p "Trotzdem '$LAN_IF' als direkten Dongle-Port einrichten? [j/N] " FORCE_LAN
        if [[ ! "$FORCE_LAN" =~ ^[JjYy]$ ]]; then
            CONFIGURE_LAN=0
            echo "LAN-Umstellung übersprungen. Stecke zuerst einen USB-WLAN-Stick oder USB-LAN-Adapter an und starte ./setup.sh erneut."
        fi
    fi

    if [ "$CONFIGURE_LAN" -eq 1 ] && [ -n "$LAN_IF" ]; then
        echo ""
        read -r -p "LAN-Schnittstelle für Direktverbindung zum WISI-Dongle [$LAN_IF]: " INPUT_LAN
        if [ -n "$INPUT_LAN" ]; then
            LAN_IF="$INPUT_LAN"
        fi
        echo "Konfiguriere $LAN_IF als direkten Dongle-Port (DHCP-Server 10.42.0.1/24)..."
        sudo nmcli connection delete wisi-dongle-lan 2>/dev/null || true
        sudo nmcli connection add type ethernet ifname "$LAN_IF" con-name wisi-dongle-lan \
            ipv4.method shared \
            ipv4.addresses 10.42.0.1/24 \
            ipv6.method ignore \
            connection.autoconnect yes \
            connection.autoconnect-priority 100
        sudo nmcli connection up wisi-dongle-lan || echo "Hinweis: Kabel noch nicht gesteckt – Verbindung startet automatisch beim Einstecken."
    elif [ -z "$LAN_IF" ]; then
        echo "Warnung: Keine Ethernet-Schnittstelle gefunden! Bitte später manuell mit nmcli einrichten."
    fi
else
    echo "=== [3/4] Netzwerkkonfiguration übersprungen (--no-network) ==="
fi

echo ""
echo "=== [4/4] Richte 24/7 systemd Hintergrund-Dienst ein ==="
SERVICE_FILE="/etc/systemd/system/wisi-server.service"

sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=WISI OR S2D DVB-over-IP 24/7 Web Control Center
After=network-online.target NetworkManager.service
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$SCRIPT_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$SCRIPT_DIR/src
ExecStart=$VENV_DIR/bin/python -m wisi_s2d.cli.ui --host 0.0.0.0 --port 8888 --no-browser --auto-connect
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable wisi-server.service
sudo systemctl restart wisi-server.service

sleep 2
HOME_IP="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -v '^10\.42\.0\.' | grep -v '^127\.' | head -n1 || true)"
if [ -z "$HOME_IP" ]; then
    HOME_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || echo 'localhost')"
fi

echo ""
echo "===================================================================="
echo "  Fertig! Der WISI OR S2D 24/7 Server läuft im Hintergrund."
echo "===================================================================="
echo "  Web-Dashboard:      http://${HOME_IP}:8888"
echo "  M3U-Senderliste:    http://${HOME_IP}:8888/playlist.m3u"
echo "  Dongle-LAN-Subnetz: 10.42.0.1/24 (DHCP-Server aktiv auf ${LAN_IF:-LAN})"
echo ""
echo "  Dienst prüfen:      sudo systemctl status wisi-server"
echo "  Live-Logs:          sudo journalctl -u wisi-server -f"
echo "  Dongle-IP prüfen:   cat /var/lib/NetworkManager/dnsmasq-*.leases"
echo "===================================================================="
