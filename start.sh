#!/bin/bash
set -e

flask db upgrade || true

python /app/seed_teacher.py || true

exec gunicorn -w 3 --threads 2 --bind 0.0.0.0:8000 wsgi:app

