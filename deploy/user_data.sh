#!/bin/bash
set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1
echo "[user-data] starting at $(date -Iseconds)"

# =========================
# קונפיג מ-GitHub Actions (אם לא הוזרק — ברירות מחדל)
# =========================
IMAGE_NAME="${IMAGE_NAME:-jonatan0897/pro_dev}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-8000}"

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
ufw disable || true

# -------------------------
# התקנת Docker Engine + Compose V2
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

# .env (Compose טוען אוטומטית)
cat > .env <<EOF
POSTGRES_DB=${POSTGRES_DB}
POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

SECRET_KEY=${SECRET_KEY}
FLASK_ENV=${FLASK_ENV}
APP_PORT=${APP_PORT}
NGINX_HOST_PORT=${NGINX_HOST_PORT}

IMAGE_NAME=${IMAGE_NAME}
IMAGE_TAG=${IMAGE_TAG}
EOF

# nginx.conf
cat > nginx/nginx.conf <<'EOF'
server {
  listen 80 default_server;
  listen [::]:80 default_server;

  proxy_set_header Host $host;
  proxy_set_header X-Real-IP $remote_addr;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;

  location / { proxy_pass http://backend:8000/; }

  location /healthz { proxy_pass http://backend:8000/healthz; }
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

echo "[user-data] docker compose pull ..."
# מושך את סטאק האפליקציה (ללא מוניטורינג)
docker compose -f docker-compose.yml pull || true

echo "[user-data] docker compose up -d (app only) ..."
docker compose -f docker-compose.yml up -d


#==========================
# המתנה ל-Health
# =========================
echo "[user-data] waiting for health..."
ok=""
for i in {1..120}; do
  sleep 5
  if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "Local Health OK (/healthz)"; ok="yes"; break
  fi
  if curl -fsS http://127.0.0.1/api/ping >/dev/null 2>&1; then
    echo "Local Health OK (/api/ping)"; ok="yes"; break
  fi
  echo "wait $i/120..."
done

if [ -z "$ok" ]; then
  echo "Health check FAILED — dumping quick diagnostics"
  docker ps
  docker compose -f docker-compose.yml ps || true
  docker compose logs --no-color --tail=200 db || true
  docker compose logs --no-color --tail=200 backend || true
  docker compose logs --no-color --tail=200 nginx || true
  exit 1
fi

# =========================
# מיגרציות + SEED אידמפוטנטי
# =========================
echo "[user-data] running migrations (flask db upgrade)..."
docker compose exec -T backend bash -lc 'export FLASK_APP=wsgi.py; flask db upgrade || python - <<PY
from app import create_app
from app.extensions import db
app = create_app()
with app.app_context():
    db.create_all()
    print("[migrate] fallback create_all done")
PY'

echo "[user-data] running seed (scripts/seed_all.py, idempotent)..."
docker compose exec -T backend python - <<'PY'
from app import create_app
from app.extensions import db
from app.models import User
try:
    from scripts.seed_all import seed_all
except Exception as e:
    print("[seed] seed_all import failed:", e); raise

app = create_app()
with app.app_context():
    exists = db.session.execute(db.select(User).limit(1)).first()
    if exists:
        print("[seed] users already exist; skipping.")
    else:
        seed_all()
        print("[seed] done.")
PY

# -------------------------
# שירות systemd להישרדות ריבוט
# -------------------------
cat > /etc/systemd/system/myapp-compose.service <<'EOF'
[Unit]
Description=MyApp via Docker Compose (App only)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/opt/myapp
ExecStart=/usr/bin/docker compose -f docker-compose.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.yml down
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable myapp-compose.service

echo "[user-data] finished OK at $(date -Iseconds)"
