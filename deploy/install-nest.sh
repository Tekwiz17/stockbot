#!/usr/bin/env bash
set -euo pipefail
# Run from the cloned repository on Nest. Does not alter other applications or proxies.
cd "$(dirname "$0")/.."
STOCKBOT_DIR="$(pwd)"
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
python3 deploy/configure.py
python3 deploy/update-origins.py
mkdir -p data
chmod 700 data
chmod 600 .env
if [ "$(id -u)" = "0" ]; then
  STOCKBOT_UNIT_DIR=/etc/systemd/system
  STOCKBOT_SYSTEMCTL=(systemctl)
  STOCKBOT_TARGET=multi-user.target
else
  STOCKBOT_UNIT_DIR="$HOME/.config/systemd/user"
  STOCKBOT_SYSTEMCTL=(systemctl --user)
  STOCKBOT_TARGET=default.target
fi
mkdir -p "$STOCKBOT_UNIT_DIR"
cat > "$STOCKBOT_UNIT_DIR/stockbot.service" <<EOF
[Unit]
Description=StockBot autonomous simulation and public ledger
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
WorkingDirectory=$STOCKBOT_DIR
EnvironmentFile=$STOCKBOT_DIR/.env
ExecStart=$STOCKBOT_DIR/.venv/bin/python -m backend.serve
Restart=on-failure
RestartSec=15
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
MemoryMax=900M
[Install]
WantedBy=$STOCKBOT_TARGET
EOF
"${STOCKBOT_SYSTEMCTL[@]}" daemon-reload
"${STOCKBOT_SYSTEMCTL[@]}" enable stockbot.service
"${STOCKBOT_SYSTEMCTL[@]}" restart stockbot.service
"${STOCKBOT_SYSTEMCTL[@]}" is-active stockbot.service
printf '%s\n' 'Backend listening on port 8765. Configure the Nest dashboard reverse proxy for stockbot.tekwiz17.hackclub.app → port 8765.'
