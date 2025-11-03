#!/bin/bash
set -euxo pipefail

# הערכים יוזרקו על-ידי ה-Workflow (דרך export לפני הסקריפט)
IMAGE_NAME="${IMAGE_NAME:-jonatan0897/myapp}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
APP_PORT="${APP_PORT:-80}"
DOCKERHUB_USERNAME="${DOCKERHUB_USERNAME}"
DOCKERHUB_TOKEN="${DOCKERHUB_TOKEN}"

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y ca-certificates curl gnupg lsb-release

# התקנת Docker Engine מהמאגר הרשמי
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $UBUNTU_CODENAME) stable" \
> /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# לא חובה, אבל נוח אם תרצה להתחבר כמשתמש ubuntu
usermod -aG docker ubuntu || true

# כניסה ל-Docker Hub כדי לא למשוך rate-limited
echo "${DOCKERHUB_TOKEN}" | docker login -u "${DOCKERHUB_USERNAME}" --password-stdin

# Service שיריץ את הקונטיינר שלך (ממפה 80 חיצוני ל-APP_PORT פנימי)
cat >/etc/systemd/system/myapp.service <<'SVC'
[Unit]
Description=MyApp container
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
Restart=always
ExecStartPre=/usr/bin/docker pull __IMAGE_NAME__:__IMAGE_TAG__
ExecStart=/usr/bin/docker run --rm \
  --name myapp \
  -p 80:__APP_PORT__ \
  __IMAGE_NAME__:__IMAGE_TAG__
ExecStop=/usr/bin/docker stop myapp

[Install]
WantedBy=multi-user.target
SVC

# החלפת משתנים בתבנית
sed -i "s#__IMAGE_NAME__#${IMAGE_NAME}#g" /etc/systemd/system/myapp.service
sed -i "s#__IMAGE_TAG__#${IMAGE_TAG}#g" /etc/systemd/system/myapp.service
sed -i "s#__APP_PORT__#${APP_PORT}#g"   /etc/systemd/system/myapp.service

systemctl daemon-reload
systemctl enable --now myapp.service

# בדיקת בריאות בסיסית אם יש /healthz
for i in {1..30}; do
  sleep 5
  if curl -fsS http://127.0.0.1/healthz >/dev/null 2>&1; then
    echo "Health OK"
    break
  fi
done
