#!/bin/bash
set -e

# Apply database migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Start the main process (Gunicorn)
exec "$@"