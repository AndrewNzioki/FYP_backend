import os
import time
import json
import logging
import django
from django.db import db_excpetions

# 1. 🚨 FIX: Boot Django context BEFORE importing models or channels
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rethink_scada.settings")  # Replace with your actual project name
django.setup()

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.models import SystemState, TankState, TelemetryLog
from django.db import transaction, close_old_connections

# Setup logging so you can see errors in Docker logs
logger = logging.getLogger(__name__)

channel_layer = get_channel_layer()
LAST_DB_WRITE = 0
DB_WRITE_INTERVAL = 60  # Seconds


def on_message(client, userdata, msg):
    global LAST_DB_WRITE
    current_time = time.time()

    # 🚨 FIX: Close stale DB connections before attempting to write
    close_old_connections()

    try:
        # Decode bytes to string, then parse JSON
        raw_payload = msg.payload.decode('utf-8')
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.error(f"POISON PILL: Dropping malformed MQTT payload: {msg.payload}")
        return  # Exit the function safely, keep the worker alive
    except Exception as e:
        logger.error(f"Unexpected error decoding payload: {e}")
        return

    # 1. ALWAYS push to Redis for the Compose App (Real-time 1Hz)
    try:
        async_to_sync(channel_layer.group_send)(
            "telemetry_group",
            {
                "type": "telemetry_update",
                "data": payload
            }
        )
    except Exception as e:
        logger.error(f"Redis/Channels failed to broadcast: {e}")

    # 2. UPDATE the "Current State" in the DB
    try:
        with transaction.atomic():
            update_current_system_state(payload)
    except Exception as e:
        logger.error(f"DB Current State Update Failed: {e}")

    # 3. THROTTLE the Historical Logging (1 Minute)
    if current_time - LAST_DB_WRITE >= DB_WRITE_INTERVAL:
        try:
            with transaction.atomic():
                log_telemetry_to_db(payload)
            LAST_DB_WRITE = current_time
        except Exception as e:
            logger.error(f"DB Historical Log Failed: {e}")


def update_current_system_state(payload):
    # Overwrite the active SystemState and related TankStates
    pass


def log_telemetry_to_db(payload):
    # Append a new row to TelemetryLog for historical charting
    pass