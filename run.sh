#!/bin/bash
set -euo pipefail

PORT="${PORT:-8090}"

# 1) Web (background)
uvicorn fidden.asgi:application --host 0.0.0.0 --port "$PORT" --ws websockets & WEB_PID=$!

# 2) Celery worker (background) — tiny footprint
celery -A fidden worker \
  -l info \
  --pool=solo \
  --concurrency=1 \
  --prefetch-multiplier=1 \
  --max-tasks-per-child=100 \
  --max-memory-per-child=120000 & WORKER_PID=$!

# 3) Celery beat (scheduler) — pick ONE scheduler source:

# OPTION A (recommended if you already defined app.conf.beat_schedule in code):
#   -> USE the in-code schedule and DO NOT pass the django_celery_beat scheduler flag.
celery -A fidden beat -l info & BEAT_PID=$!

# OPTION B (if you want to manage schedules in Django Admin):
#   -> COMMENT the line above and UNCOMMENT the line below,
#      but then you MUST create a PeriodicTask row for each task.
# celery -A fidden beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler & BEAT_PID=$!

# Graceful shutdown
trap "kill -TERM $WEB_PID $WORKER_PID $BEAT_PID 2>/dev/null || true" TERM INT
wait -n $WEB_P
ID $WORKER_PID $BEAT_PID
kill -TERM $WEB_PID $WORKER_PID $BEAT_PID 2>/dev/null || true
wait
