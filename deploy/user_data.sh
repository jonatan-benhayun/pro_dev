#!/bin/bash
set -euxo pipefail
exec > >(tee -a /var/log/user-data.log) 2>&1
echo "[user-data] starting at $(date -Iseconds)"

# =========================
# קונפיג מה-Workflow (secrets)
# =========================
IMAGE_NAME="${IMAGE_NAME:-jonatan0897/pro_dev}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-8000}"
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME:-}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN:-}"

export DEBIAN_FRONTEND=noninteractive

# -------------------------
# עדכונים וכלי בסיס
# -------------------------
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release git

ufw disable || true

# -------------------------
# התקנת Docker Engine רשמי + compose plugin
# -------------------------
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

usermod -aG docker ubuntu || true
systemctl enable docker
systemctl start docker

# -------------------------
# Login ל-Docker Hub (להימנע מ-rate limit)
# -------------------------
if [ -n "${DOCKERHUB_USERNAME}" ] && [ -n "${DOCKERHUB_TOKEN}" ]; then
  echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin
fi

# -------------------------
# הורדת הקוד מה-GitHub (ה-compose.yml אמור להיות שם)
# -------------------------
mkdir -p /opt/app
cd /opt/app

# אם הריפו שלך פרטי, אפשר להשתמש ב-token, אבל נניח שהוא ציבורי:
git clone https://github.com/jonatan-benhayun/pro_dev.git .
echo "[user-data] Repository cloned."

# -------------------------
# הפעלת הסביבה עם Docker Compose
# -------------------------
echo "[user-data] Pulling images..."
docker compose pull

echo "[user-data] Starting containers..."
docker compose up -d

# -------------------------
# המתנה לבדוק שהאפליקציה עלתה
# -------------------------
ok=""
for i in {1..120}; do
  sleep 5
  if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "[user-data] Local Health OK"
    ok="yes"
    break
  fi
  echo "[user-data] Waiting for app startup ($i/120)..."
done

docker compose ps
docker ps

if [ -z "$ok" ]; then
  echo "[user-data] Health check failed (no /healthz on localhost)"
  docker compose logs backend || true
  docker compose logs nginx || true
  exit 1
fi

echo "[user-data] Finished successfully!"
