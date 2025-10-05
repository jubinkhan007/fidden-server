#!/bin/sh
set -e

# Ensure static directory exists
mkdir -p /app/staticfiles
mkdir -p /app/media

# Clean STATIC_ROOT before collectstatic (optional but safe)
rm -rf /app/staticfiles/*

# Apply database migrations
echo "Applying database migrations..."
python manage.py migrate --noinput

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Start Celery worker in background if requested
if [ "$RUN_CELERY" = "true" ]; then
    echo "Starting Celery worker..."
    celery -A fidden worker --loglevel=info &
fi

# Start Celery Beat in background if requested
if [ "$RUN_BEAT" = "true" ]; then
    echo "Starting Celery Beat..."
    celery -A fidden beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler &
fi

# Run Gunicorn (CMD from Dockerfile)
exec "$@"