#!/usr/bin/env bash
# Deploy VBots to Linux server at 192.168.11.226
# Run from the vbots project root on your Windows machine (Git Bash or WSL)
#
# Usage:
#   bash deploy.sh                         # deploys to root@192.168.11.226
#   bash deploy.sh ubuntu@192.168.11.226    # custom user

set -e
SERVER="${1:-root@192.168.11.226}"
REMOTE_DIR="/opt/vbots"

echo "==> Syncing files to $SERVER:$REMOTE_DIR ..."
rsync -avz --progress \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='backend/data/' \
  --exclude='frontend/dist/' \
  . "$SERVER:$REMOTE_DIR/"

echo ""
echo "==> Running deployment on $SERVER ..."
ssh "$SERVER" bash <<REMOTE
set -e
cd $REMOTE_DIR

# ── Firewall ─────────────────────────────────────────────────────────────
if command -v ufw &>/dev/null; then
  ufw allow 80/tcp    comment 'Nginx'      2>/dev/null || true
  ufw allow 7880/tcp  comment 'LiveKit WS' 2>/dev/null || true
  ufw allow 7881/tcp  comment 'LiveKit RTC TCP' 2>/dev/null || true
  ufw allow 5060/udp  comment 'SIP UDP'   2>/dev/null || true
  ufw allow 5060/tcp  comment 'SIP TCP'   2>/dev/null || true
  ufw allow 3478/udp  comment 'TURN UDP'  2>/dev/null || true
  ufw allow 3478/tcp  comment 'TURN TCP'  2>/dev/null || true
  ufw allow 5349/tcp  comment 'TURN TLS'  2>/dev/null || true
  ufw allow 50000:60000/udp comment 'LiveKit RTC UDP' 2>/dev/null || true
  echo "Firewall rules applied"
fi

# ── .env ─────────────────────────────────────────────────────────────────
if [ ! -f backend/.env ]; then
  echo ""
  echo "WARNING: backend/.env not found on server."
  echo "Copy it manually:  scp backend/.env $SERVER:$REMOTE_DIR/backend/.env"
  echo "Then re-run this script."
  exit 1
fi

# ── Build & start ─────────────────────────────────────────────────────────
echo "Building images (this takes a few minutes first time)..."
docker compose -f docker-compose.prod.yml build --no-cache

echo "Starting stack..."
docker compose -f docker-compose.prod.yml up -d

echo ""
echo "==> Service status:"
docker compose -f docker-compose.prod.yml ps
REMOTE

echo ""
echo "==> Deployment complete!"
echo ""
echo "    Frontend  : http://192.168.11.226"
echo "    API docs  : http://192.168.11.226/docs"
echo "    API direct: http://192.168.11.226:8000"
echo "    LiveKit   : ws://192.168.11.226:7880"
echo ""
echo "    Watch logs: ssh $SERVER 'cd $REMOTE_DIR && docker compose -f docker-compose.prod.yml logs -f worker'"
