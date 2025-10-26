#!/usr/bin/env bash
set -euo pipefail

PORT="${NGINX_HOST_PORT:-80}"
PATH_TO_CHECK="${BACKEND_CHECK_PATH:-/api/ping}"
BASE="http://localhost:${PORT}"

echo "==> מחכה ל-Nginx ב ${BASE}/healthz"
MAX=180; SLEEP=2
for i in $(seq 1 "$MAX"); do
  if curl -fsS "${BASE}/healthz" >/dev/null; then echo "OK: Nginx חי"; break; fi
  echo "[$i/$MAX] מחכה ל-nginx ..."; sleep "$SLEEP"
  [[ "$i" == "$MAX" ]] && echo "ERROR: nginx לא עלה בזמן" >&2 && exit 1
done

echo "==> מחכה ל-backend דרך Nginx ב ${BASE}${PATH_TO_CHECK}"
for i in $(seq 1 "$MAX"); do
  if curl -fsS "${BASE}${PATH_TO_CHECK}" >/dev/null; then echo "OK: backend חי"; break; fi
  echo "[$i/$MAX] מחכה ל-backend ..."; sleep "$SLEEP"
  [[ "$i" == "$MAX" ]] && echo "ERROR: backend לא עלה בזמן" >&2 && exit 1
done

echo "==> קורא ל- ${BASE}${PATH_TO_CHECK}"
RESP="$(curl -fsS "${BASE}${PATH_TO_CHECK}")" || {
  echo "בקשה נכשלה אל ${BASE}${PATH_TO_CHECK}" >&2; exit 1; }

echo "Response: ${RESP}"

# אסרטים אופציונליים
if [[ -n "${EXPECT_PATTERN1:-}" ]]; then
  echo "${RESP}" | grep -Eq "${EXPECT_PATTERN1}" || {
    echo "לא נמצא EXPECT_PATTERN1: ${EXPECT_PATTERN1}" >&2; exit 1; }
fi
if [[ -n "${EXPECT_PATTERN2:-}" ]]; then
  echo "${RESP}" | grep -Eq "${EXPECT_PATTERN2}" || {
    echo "לא נמצא EXPECT_PATTERN2: ${EXPECT_PATTERN2}" >&2; exit 1; }
fi

echo "E2E smoke test passed."
