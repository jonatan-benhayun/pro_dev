#!/usr/bin/env bash
set -euo pipefail

echo "[deploy] pulling images..."
docker pull jonatan0897/pro_dev:backend-latest || true
docker pull nginx:alpine || true

echo "[deploy] compose up"
docker compose -f /opt/app/compose/docker-compose.prod.yml up -d --remove-orphans --force-recreate

echo "[deploy] prune old"
docker system prune -f || true

echo "[deploy] done"
