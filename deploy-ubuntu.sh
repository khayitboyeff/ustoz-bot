#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/cyberustozbot/app"
SERVICE_NAME="cyberustozbot"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Bu skriptni sudo bilan ishga tushiring: sudo bash deploy-ubuntu.sh"
  exit 1
fi
if [[ ! -f "${APP_DIR}/.env" ]]; then
  echo "${APP_DIR}/.env topilmadi. Avval .env.example faylidan .env yarating va BOT_TOKEN hamda ADMIN_IDS ni kiriting."
  exit 1
fi

if ! id cyberbot >/dev/null 2>&1; then
  useradd --system --home-dir "${APP_DIR}" --shell /usr/sbin/nologin cyberbot
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip build-essential ca-certificates
mkdir -p "${APP_DIR}/database" "${APP_DIR}/backups" "${APP_DIR}/logs" "${APP_DIR}/certificates" "${APP_DIR}/reports"
chmod 700 "${APP_DIR}"
chmod 600 "${APP_DIR}/.env"
chown -R cyberbot:cyberbot "${APP_DIR}"

sudo -u cyberbot python3 -m venv "${APP_DIR}/.venv"
sudo -u cyberbot "${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip
sudo -u cyberbot "${APP_DIR}/.venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=CyberUstozBot Telegram bot
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=cyberbot
Group=cyberbot
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/bot.py
Restart=on-failure
RestartSec=5
TimeoutStopSec=30
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=${APP_DIR}/database ${APP_DIR}/backups ${APP_DIR}/logs ${APP_DIR}/certificates ${APP_DIR}/reports
LockPersonality=true
RestrictSUIDSGID=true

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
sleep 2
systemctl --no-pager --full status "${SERVICE_NAME}" || true
echo
echo "Tayyor. Log: sudo journalctl -u ${SERVICE_NAME} -f"
echo "Holat: sudo systemctl status ${SERVICE_NAME}"
