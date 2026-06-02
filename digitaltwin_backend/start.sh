#!/bin/bash
set -e

echo "=== Starting Main Web Server (Daphne) ==="
# We removed Celery, MQTT, and Migrations from here.
# Docker Compose will handle them separately!
daphne -b 0.0.0.0 -p ${PORT:-8000} --proxy-headers --access-log /dev/null digitaltwin_backend.asgi:application