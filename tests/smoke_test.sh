#!/usr/bin/env bash
set -euo pipefail

# הגדרות (ניתן לשנות עם משתני סביבה):
PORT="${NGINX_HOST_PORT:-80}"           # פורט ה-Nginx על המארח
PATH_TO_CHECK="${BACKEND_CHECK_PATH:-/}" # הנתיב שנבדוק דרך Nginx (ברירת מחדל '/')
BASE="http://localhost:${PORT}"

echo "==> מחכה ש-Nginx יעלה ב- ${BASE}/healthz"
MAX=90; SLEEP=2
for i in $(seq 1 "$MAX"); do
  if curl -fsS "${BASE}/healthz" > /dev/null; then
    echo "OK: Nginx חי"
    break
  fi
  echo "[${i}/${MAX}] מחכה ל- ${BASE}/healthz ..."
  sleep "$SLEEP"
  if [[ "$i" == "$MAX" ]]; then
    echo "ERROR: Nginx לא עלה בזמן" >&2
    exit 1
  fi
done

echo "==> קורא ל- ${BASE}${PATH_TO_CHECK}"
RESP="$(curl -fsS "${BASE}${PATH_TO_CHECK}")" || {
  echo "בקשה נכשלה אל ${BASE}${PATH_TO_CHECK}" >&2; exit 1; }

echo "Response: ${RESP}"

# אם תרצה לבדוק תבניות (Regex) בתגובה, הגדר EXPECT_PATTERN1/2 בסביבה
if [[ -n "${EXPECT_PATTERN1:-}" ]]; then
  echo "${RESP}" | grep -Eq "${EXPECT_PATTERN1}" || {
    echo "לא נמצא EXPECT_PATTERN1: ${EXPECT_PATTERN1}" >&2; exit 1; }
fi
if [[ -n "${EXPECT_PATTERN2:-}" ]]; then
  echo "${RESP}" | grep -Eq "${EXPECT_PATTERN2}" || {
    echo "לא נמצא EXPECT_PATTERN2: ${EXPECT_PATTERN2}" >&2; exit 1; }
fi

echo "E2E smoke test passed."
