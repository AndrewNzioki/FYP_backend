#!/bin/bash
# Exit immediately if any command fails
set -e

echo "=== Running Database Migrations ==="
python manage.py migrate --noinput

echo "=== Ensuring Superuser Exists ==="
# We use || true to prevent the script from crashing if the user already exists.
# It will attempt to create the user, and if Django throws an error (because it exists),
# Bash will just print the echo statement and keep moving.
python manage.py createsuperuser --noinput || echo "Superuser already exists, skipping."

echo "=== Starting Celery Worker (Background) ==="
celery -A digitaltwin_backend worker --loglevel=info &

echo "=== Starting MQTT Listener (Background) ==="
python manage.py run_mqtt &

echo "=== Starting ASGI Web Server (Foreground) ==="
daphne -b 0.0.0.0 -p ${PORT:-8000} digitaltwin_backend.asgi:application