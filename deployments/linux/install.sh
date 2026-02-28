#!/bin/bash

# AditivaFlow Hub - Linux Installer
# This script installs the Hub as a background service using systemd.

set -e

echo "------------------------------------------------"
echo "   AditivaFlow Hub - Linux Installer"
echo "------------------------------------------------"

# Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root (use sudo)"
  exit 1
fi

# Configuration
INSTALL_DIR="/opt/aditivaflow-hub"
REPO_URL="https://github.com/gabrielbolzani/3d_printer_connection_hub.git"
USER_NAME=$SUDO_USER
if [ -z "$USER_NAME" ]; then
    USER_NAME=$(whoami)
fi

echo "Installing for user: $USER_NAME"
echo "Installation directory: $INSTALL_DIR"

# 1. Install System Dependencies
echo "Step 1: Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl

# 2. Clone or Update Repository
if [ -d "$INSTALL_DIR" ]; then
    echo "Step 2: Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull
else
    echo "Step 2: Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Setup Virtual Environment
echo "Step 3: Setting up virtual environment..."
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 4. Fix permissions
echo "Step 4: Setting permissions..."
chown -R "$USER_NAME":"$USER_NAME" "$INSTALL_DIR"

# 5. Create Systemd Service
echo "Step 5: Creating systemd service..."
cat <<EOF > /etc/systemd/system/aditivaflow-hub.service
[Unit]
Description=AditivaFlow 3D Printer Hub
After=network.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python $INSTALL_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and Start Service
echo "Step 6: Starting service..."
systemctl daemon-reload
systemctl enable aditivaflow-hub
systemctl restart aditivaflow-hub

echo "------------------------------------------------"
echo "DONE! AditivaFlow Hub is now running."
echo "Access it at: http://localhost:5000"
echo "Check status: sudo systemctl status aditivaflow-hub"
echo "View logs: journalctl -u aditivaflow-hub -f"
echo "------------------------------------------------"
