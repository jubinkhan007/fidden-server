#!/usr/bin/env bash
set -euo pipefail

# 1) Start Celery worker in the background
celery -A fidden worker \
  -l info \
  --pool=solo \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 &

# 2) Start Celery Beat in the foreground (keeps container alive)
#    Uses the schedule in fidden/celery.py (app.conf.beat_schedule)
exec celery -A fidden beat -l info
