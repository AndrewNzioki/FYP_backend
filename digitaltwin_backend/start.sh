#!/bin/bash
set -e

echo "=== Migrating ==="
python manage.py migrate --noinput

echo "=== Superuser ==="
python manage.py createsuperuser --noinput || echo "Skipping superuser"

echo "=== Starting Celery (VLC Mode: 1 Worker Only) ==="
# --concurrency=1 prevents Celery from spawning multiple child processes
# --max-tasks-per-child=10 keeps memory leaks from growing
celery -A digitaltwin_backend worker --loglevel=info --concurrency=1 --max-tasks-per-child=10 &

echo "=== Starting MQTT Listener ==="
python manage.py run_mqtt &

echo "=== Starting ASGI Server ==="
# Use 1 worker for Daphne to save RAM
daphne -b 0.0.0.0 -p ${PORT:-8000} --access-log /dev/null digitaltwin_backend.asgi:application