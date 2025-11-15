#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8090}"   # Render provides PORT; fallback for local runs

# 1) Start Uvicorn web server (background)
uvicorn fidden.asgi:application \
  --host 0.0.0.0 \
  --port "$PORT" \
  --ws websockets &

# 2) Start a lightweight Celery worker (background)
celery -A fidden worker \
  -l info \
  --pool=solo \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 &

# 3) Start Celery Beat in the foreground (keeps container alive)
#    Uses the in-code schedule from fidden/celery.py (app.conf.beat_schedule)
exec celery -A fidden beat -l info
