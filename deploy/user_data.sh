#!/bin/bash
set -euxo pipefail

# =========================
# קונפיג מה-Workflow (secrets)
# =========================
IMAGE_NAME="${IMAGE_NAME:-jonatan0897/pro_dev}"   # דוגמה: jonatan0897/pro_dev
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-8000}"                      # הקונטיינר מאזין ל-8000; נמפה ל-80
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"

# =========================
# DB לוקלי (פשוט וזול להתחלה)
# =========================
DB_NAME="pro_dev"
DB_USER="prodev"
DB_PASS="prodevpass"

export DEBIAN_FRONTEND=noninteractive

# -------------------------
# בסיס: עדכונים וכלי עזר
# -------------------------
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

# אם UFW פעיל — נשבית (ה-SG של AWS מגן עלינו)
ufw disable || true

# -------------------------
# התקנת Docker Engine רשמי
# -------------------------
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) stable" > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker ubuntu || true
systemctl enable docker
systemctl start docker

# -------------------------
# Login ל-Docker Hub (ימנע rate-limit)
# -------------------------
if [ -n "${DOCKERHUB_USERNAME}" ] && [ -n "${DOCKERHUB_TOKEN}" ]; then
  echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
fi

# -------------------------
# רשת משותפת לאפליקציה ול-DB
# -------------------------
docker network create myapp-net || true

# -------------------------
# Postgres מקומי כ־service מתמיד
# -------------------------
docker rm -f db || true
docker run -d --name db --network myapp-net \
  --restart unless-stopped \
  -e POSTGRES_DB="${DB_NAME}" \
  -e POSTGRES_USER="${DB_USER}" \
  -e POSTGRES_PASSWORD="${DB_PASS}" \
  -v /var/lib/postgresql/data:/var/lib/postgresql/data \
  postgres:16-alpine

# המתנה ש-DB מוכן
for i in {1..60}; do
  if docker exec db pg_isready -U "${DB_USER}" >/dev/null 2>&1; then
    echo "DB ready"
    break
  fi
  echo "Waiting for DB... ($i/60)"
  sleep 3
done

# -------------------------
# systemd service לאפליקציה
# -------------------------
cat >/etc/systemd/system/myapp.service <<'SVC'
[Unit]
Description=MyApp container
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
Restart=always
# מושך את האימג' לפני הרצה
ExecStartPre=/usr/bin/docker pull __IMAGE_NAME__:__IMAGE_TAG__
# מריץ את הקונטיינר על אותה רשת כמו ה-DB, עם מיפוי פורט 80 חיצוני ל-APP_PORT פנימי
ExecStart=/usr/bin/docker run --rm \
  --name myapp \
  --network myapp-net \
  -e DATABASE_URL=postgresql+psycopg2://__DB_USER__:__DB_PASS__@db:5432/__DB_NAME__ \
  -e APP_PORT=__APP_PORT__ \
  -p 80:__APP_PORT__ \
  __IMAGE_NAME__:__IMAGE_TAG__
ExecStop=/usr/bin/docker stop myapp

[Install]
WantedBy=multi-user.target
SVC

# החלפת פלייסהולדרים
sed -i "s#__IMAGE_NAME__#${IMAGE_NAME}#g" /etc/systemd/system/myapp.service
sed -i "s#__IMAGE_TAG__#${IMAGE_TAG}#g"   /etc/systemd/system/myapp.service
sed -i "s#__APP_PORT__#${APP_PORT}#g"     /etc/systemd/system/myapp.service
sed -i "s#__DB_NAME__#${DB_NAME}#g"       /etc/systemd/system/myapp.service
sed -i "s#__DB_USER__#${DB_USER}#g"       /etc/systemd/system/myapp.service
sed -i "s#__DB_PASS__#${DB_PASS}#g"       /etc/systemd/system/myapp.service

systemctl daemon-reload
systemctl enable --now myapp.service

# -------------------------
# בריאות מקומית + לוגים לעזרה
# -------------------------
# נמתין עד 10 דקות כי משיכת אימג' והקמה ראשונית עלולות לקחת זמן
ok=""
for i in {1..120}; do  # 120*5s = 10 דקות
  sleep 5
  if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "Local Health OK"
    ok="yes"
    break
  fi
  echo "Local wait $i..."
done

# דיאגנוסטיקה בסיסית לקונסול אם יש כשל
systemctl status myapp --no-pager || true
journalctl -u myapp -n 100 --no-pager || true
docker ps || true

if [ -z "$ok" ]; then
  echo "Health check failed (no /healthz on localhost)"
  exit 1
fi

echo "User-data finished successfully."
