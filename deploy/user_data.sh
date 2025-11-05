#!/bin/bash
set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1
echo "[user-data] starting at $(date -Iseconds)"

# =========================
# קונפיג מ-GitHub Actions (אם לא הוזרק — שמים ברירות מחדל בטוחות)
# =========================
IMAGE_NAME="${IMAGE_NAME:-jonatan0897/pro_dev}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-8000}"

# אופציונלי: התחברות לדוקר האב למניעת rate limit
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"

# DB (לוקלי בתוך השרת)
POSTGRES_DB="${POSTGRES_DB:-pro_dev}"
POSTGRES_USER="${POSTGRES_USER:-prodev}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-prodevpass}"

# אפליקציה
SECRET_KEY="${SECRET_KEY:-$(head -c 32 /dev/urandom | base64)}"
FLASK_ENV="${FLASK_ENV:-production}"
NGINX_HOST_PORT="${NGINX_HOST_PORT:-80}"

export DEBIAN_FRONTEND=noninteractive

# -------------------------
# בסיס: עדכונים וכלי עזר
# -------------------------
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release jq

# אם UFW פעיל — נשבית (ה-Security Group של AWS מגן עלינו)
ufw disable || true

# -------------------------
# התקנת Docker Engine רשמי + Compose V2
# -------------------------
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker ubuntu || true
systemctl enable --now docker

# -------------------------
# Login ל-Docker Hub (אם סופקו סודות)
# -------------------------
if [ -n "$DOCKERHUB_USERNAME" ] && [ -n "$DOCKERHUB_TOKEN" ]; then
  echo "$DOCKERHUB_TOKEN" | docker login -u "$DOCKERHUB_USERNAME" --password-stdin || true
fi

# -------------------------
# פרויקט: קבצים, .env, compose ו-nginx
# -------------------------
mkdir -p /opt/myapp/nginx
cd /opt/myapp

# .env לכל השירותים (compose יטען אוטומטית)
cat > .env <<EOF
# ===== DB =====
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# ===== App =====
SECRET_KEY=${SECRET_KEY}
FLASK_ENV=${FLASK_ENV}
APP_PORT=${APP_PORT}
NGINX_HOST_PORT=${NGINX_HOST_PORT}

# נוח אם נרצה לבנות/למשוך:
IMAGE_NAME=${IMAGE_NAME}
IMAGE_TAG=${IMAGE_TAG}
EOF

# nginx.conf (reverse proxy ל-backend:8000)
cat > nginx/nginx.conf <<'EOF'
server {
  listen 80 default_server;
  listen [::]:80 default_server;

  # X-Forwarded-* ל-Flask
  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;

  location / {
    proxy_pass http://backend:8000/;
  }

  # בריאות נוחה
  location /healthz {
    proxy_pass http://backend:8000/healthz;
  }
}
EOF

# docker-compose.yml – backend מה-Docker Hub; DB לוקלי; NGINX מקדימה
cat > docker-compose.yml <<'EOF'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL","pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 3s
      retries: 30
    restart: unless-stopped
    networks: [appnet]

  backend:
    image: ${IMAGE_NAME}:${IMAGE_TAG}
    environment:
      SECRET_KEY: ${SECRET_KEY}
      FLASK_ENV: ${FLASK_ENV}
      APP_PORT: ${APP_PORT}
      DATABASE_URL: postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
    depends_on:
      db:
        condition: service_healthy
    expose:
      - "8000"
    healthcheck:
      test: ["CMD-SHELL","python -c 'import urllib.request,sys; urllib.request.urlopen(\"http://localhost:8000/api/ping\", timeout=3); sys.exit(0)' || exit 1"]
      interval: 5s
      timeout: 3s
      retries: 60
    restart: unless-stopped
    networks: [appnet]

  nginx:
    image: nginx:stable-alpine
    ports:
      - "${NGINX_HOST_PORT:-80}:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      backend:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL","wget -qO- http://backend:8000/api/ping | grep -q 'status'"]
      interval: 5s
      timeout: 3s
      retries: 30
    restart: unless-stopped
    networks: [appnet]

volumes:
  pgdata: {}

networks:
  appnet:
    driver: bridge
EOF

# -------------------------
# הרצה ראשונית + בדיקות
# -------------------------
echo "[user-data] docker compose pull (מושך תמונות אם צריך)..."
docker compose pull || true

echo "[user-data] docker compose up -d ..."
docker compose up -d

# המתנה עד 10 דקות לבריאות
echo "[user-data] waiting for health..."
ok=""
for i in {1..120}; do
  sleep 5
  if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "Local Health OK (/healthz)"
    ok="yes"
    break
  fi
  # ניסיון גיבוי דרך ה-backend ישירות
  if curl -fsS http://127.0.0.1/api/ping >/dev/null 2>&1; then
    echo "Local Health OK (/api/ping)"
    ok="yes"
    break
  fi
  echo "wait $i/120..."
done

# דיאגנוסטיקה במקרה כשל
if [ -z "$ok" ]; then
  echo "Health check FAILED — dumping quick diagnostics"
  docker ps
  docker compose ps
  docker compose logs --no-color --tail=200 db || true
  docker compose logs --no-color --tail=200 backend || true
  docker compose logs --no-color --tail=200 nginx || true
  exit 1
fi

# -------------------------
# שירות systemd שירים את ה-compose אחרי Reboot
# -------------------------
cat > /etc/systemd/system/myapp-compose.service <<'EOF'
[Unit]
Description=MyApp via Docker Compose
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/myapp
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable myapp-compose.service

echo "[user-data] finished OK at $(date -Iseconds)"
