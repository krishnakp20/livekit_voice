#!/usr/bin/env bash
# VBots — Full Native Setup (no Docker) for Ubuntu 22.04 / Debian 12
# Run as root on 192.168.11.226:
#   bash setup-server.sh
set -e

APP_DIR="/opt/vbots"
VENV="$APP_DIR/backend/.venv"
SERVER_IP="192.168.11.226"

echo "======================================================"
echo " VBots Native Setup — $SERVER_IP"
echo "======================================================"

# ── 1. System packages ────────────────────────────────────
echo "[1/8] Installing system packages..."
apt-get update -qq
apt-get install -y --no-install-recommends \
  curl wget git unzip build-essential \
  python3.12 python3.12-venv python3.12-dev python3-pip \
  mysql-server redis-server nginx \
  pkg-config default-libmysqlclient-dev \
  supervisor

# Node.js 20 (for frontend build)
if ! command -v node &>/dev/null; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi
echo "  Python: $(python3.12 --version)  Node: $(node --version)"

# ── 2. MySQL setup ────────────────────────────────────────
echo "[2/8] Setting up MySQL..."
systemctl enable --now mysql

mysql -u root <<'SQL'
CREATE DATABASE IF NOT EXISTS vbots CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'vbots'@'localhost' IDENTIFIED BY 'vbots';
GRANT ALL PRIVILEGES ON vbots.* TO 'vbots'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "  MySQL: vbots database ready"

# ── 3. Redis ──────────────────────────────────────────────
echo "[3/8] Starting Redis..."
systemctl enable --now redis-server
echo "  Redis: $(redis-cli ping)"

# ── 4. LiveKit server binary ──────────────────────────────
echo "[4/8] Installing LiveKit server..."
LK_VERSION="v1.8.3"
if [ ! -f /usr/local/bin/livekit-server ]; then
  wget -q "https://github.com/livekit/livekit/releases/download/${LK_VERSION}/livekit_linux_amd64.tar.gz" \
    -O /tmp/livekit.tar.gz
  tar -xzf /tmp/livekit.tar.gz -C /usr/local/bin livekit-server
  chmod +x /usr/local/bin/livekit-server
  rm /tmp/livekit.tar.gz
fi
echo "  LiveKit: $(/usr/local/bin/livekit-server --version 2>&1 | head -1)"

# Copy livekit config (update redis address for native setup)
mkdir -p /etc/livekit
cp "$APP_DIR/infra/livekit-prod.yaml" /etc/livekit/livekit.yaml
# For native: redis is on localhost (not a Docker service name)
sed -i 's/address: .*/address: 127.0.0.1:6379/' /etc/livekit/livekit.yaml
echo "  Config: /etc/livekit/livekit.yaml"

# ── 5. Python virtual environment ────────────────────────
echo "[5/8] Setting up Python venv..."
python3.12 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q

"$VENV/bin/pip" install -q -r "$APP_DIR/backend/requirements.txt"
"$VENV/bin/pip" install -q \
  "livekit-agents[silero]>=1.5,<2.0" \
  "livekit-plugins-openai>=1.5,<2.0" \
  "livekit-plugins-sarvam>=1.5,<2.0"

echo "  Venv: $VENV"

# ── 6. Build frontend ─────────────────────────────────────
echo "[6/8] Building React frontend..."
cd "$APP_DIR/frontend"
npm install --silent
npm run build
echo "  Frontend built: $APP_DIR/frontend/dist"

# ── 7. Nginx ─────────────────────────────────────────────
echo "[7/8] Configuring Nginx..."
cat > /etc/nginx/sites-available/vbots << NGINX
server {
    listen 80;
    server_name $SERVER_IP;
    client_max_body_size 50M;

    # API
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 120s;
    }

    # FastAPI docs
    location /docs { proxy_pass http://127.0.0.1:8000; }
    location /openapi.json { proxy_pass http://127.0.0.1:8000; }

    # Socket.IO (live calls dashboard)
    location /socket.io/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }

    # React SPA (static build)
    location / {
        root $APP_DIR/frontend/dist;
        try_files \$uri \$uri/ /index.html;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/vbots /etc/nginx/sites-enabled/vbots
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable --now nginx
systemctl reload nginx
echo "  Nginx: ready"

# ── 8. Systemd services ───────────────────────────────────
echo "[8/8] Creating systemd services..."

# ── livekit.service ──────────────────────────────────────
cat > /etc/systemd/system/livekit.service << 'EOF'
[Unit]
Description=LiveKit Server
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
ExecStart=/usr/local/bin/livekit-server --config /etc/livekit/livekit.yaml
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── vbots-api.service ─────────────────────────────────────
cat > /etc/systemd/system/vbots-api.service << EOF
[Unit]
Description=VBots FastAPI
After=network.target mysql.service redis-server.service livekit.service
Wants=mysql.service redis-server.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
Environment=PYTHONPATH=$APP_DIR/backend
Environment=DATABASE_URL=mysql+aiomysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4
Environment=DATABASE_URL_SYNC=mysql+pymysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4
Environment=REDIS_URL=redis://localhost:6379/0
Environment=CELERY_BROKER_URL=redis://localhost:6379/1
Environment=CELERY_RESULT_BACKEND=redis://localhost:6379/2
Environment=LIVEKIT_URL=ws://localhost:7880
ExecStartPre=$VENV/bin/python scripts/seed.py
ExecStart=$VENV/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── vbots-worker.service ──────────────────────────────────
cat > /etc/systemd/system/vbots-worker.service << EOF
[Unit]
Description=VBots LiveKit Agent Worker
After=network.target livekit.service vbots-api.service
Wants=livekit.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
Environment=PYTHONPATH=$APP_DIR/backend
Environment=DATABASE_URL=mysql+aiomysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4
Environment=REDIS_URL=redis://localhost:6379/0
Environment=LIVEKIT_URL=ws://localhost:7880
ExecStart=$VENV/bin/python worker/agent.py start
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── vbots-celery-worker.service ───────────────────────────
cat > /etc/systemd/system/vbots-celery-worker.service << EOF
[Unit]
Description=VBots Celery Worker
After=network.target redis-server.service mysql.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
Environment=PYTHONPATH=$APP_DIR/backend
Environment=DATABASE_URL=mysql+aiomysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4
Environment=DATABASE_URL_SYNC=mysql+pymysql://vbots:vbots@localhost:3306/vbots?charset=utf8mb4
Environment=CELERY_BROKER_URL=redis://localhost:6379/1
Environment=CELERY_RESULT_BACKEND=redis://localhost:6379/2
ExecStart=$VENV/bin/celery -A app.tasks.celery_app worker --loglevel=info --concurrency=4
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── vbots-celery-beat.service ─────────────────────────────
cat > /etc/systemd/system/vbots-celery-beat.service << EOF
[Unit]
Description=VBots Celery Beat Scheduler
After=network.target redis-server.service vbots-celery-worker.service

[Service]
Type=simple
WorkingDirectory=$APP_DIR/backend
EnvironmentFile=$APP_DIR/backend/.env
Environment=PYTHONPATH=$APP_DIR/backend
Environment=CELERY_BROKER_URL=redis://localhost:6379/1
Environment=CELERY_RESULT_BACKEND=redis://localhost:6379/2
ExecStart=$VENV/bin/celery -A app.tasks.celery_app beat --loglevel=info
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── Enable and start all ──────────────────────────────────
systemctl daemon-reload
systemctl enable livekit vbots-api vbots-worker vbots-celery-worker vbots-celery-beat

systemctl start livekit
sleep 3
systemctl start vbots-api
sleep 5
systemctl start vbots-worker vbots-celery-worker vbots-celery-beat

echo ""
echo "======================================================"
echo " Setup complete! Checking services..."
echo "======================================================"
sleep 3

for svc in mysql redis-server livekit nginx vbots-api vbots-worker vbots-celery-worker vbots-celery-beat; do
  status=$(systemctl is-active "$svc" 2>/dev/null || echo "not-found")
  printf "  %-30s %s\n" "$svc" "$status"
done

echo ""
echo "  Dashboard : http://$SERVER_IP"
echo "  API docs  : http://$SERVER_IP/docs"
echo "  Logs      : journalctl -u vbots-worker -f"
echo ""
