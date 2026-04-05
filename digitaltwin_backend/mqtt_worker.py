import time
import json
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.models import SystemState, TankState, TelemetryLog

channel_layer = get_channel_layer()
LAST_DB_WRITE = 0
DB_WRITE_INTERVAL = 60 # Seconds

def on_message(client, userdata, msg):
    global LAST_DB_WRITE
    current_time = time.time()
    payload = json.loads(msg.payload)

    # 1. ALWAYS push to Redis for the Compose App (Real-time 1Hz)
    async_to_sync(channel_layer.group_send)(
        "telemetry_group",
        {
            "type": "telemetry_update",
            "data": payload
        }
    )

    # 2. UPDATE the "Current State" in the DB (Overwrites the single active row)
    # This ensures your REST API always has the latest snapshot without bloating history.
    update_current_system_state(payload) 

    # 3. THROTTLE the Historical Logging (1 Minute)
    if current_time - LAST_DB_WRITE >= DB_WRITE_INTERVAL:
        log_telemetry_to_db(payload)
        LAST_DB_WRITE = current_time

def update_current_system_state(payload):
    # Overwrite the active SystemState and related TankStates
    pass 

def log_telemetry_to_db(payload):
    # Append a new row to TelemetryLog for historical charting
    pass