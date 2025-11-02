#!/usr/bin/env bash
set -euo pipefail

PORT="${NGINX_HOST_PORT:-8000}"
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
RESP="$(curl -fsS "${BASE}${PATH_TO_CHECK}")"
echo "Response: ${RESP}"

# אימות JSON: status == ok AND db == connected (בלי תלות בסדר/רווחים)
python3 - << 'PY' "${RESP}"
import sys, json
raw = sys.argv[1]
try:
    data = json.loads(raw)
except Exception as e:
    print("ERROR: invalid JSON:", e); sys.exit(1)
status_ok = (str(data.get("status")) == "ok")
db_ok = (str(data.get("db")) == "connected")
if status_ok and db_ok:
    print("JSON check passed.")
    sys.exit(0)
print("JSON check failed. Got:", data); sys.exit(1)
PY

echo "E2E smoke test passed."
