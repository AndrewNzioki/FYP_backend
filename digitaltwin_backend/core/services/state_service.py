"""State and telemetry persistence for edge-authoritative SCADA mode."""

import time
import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction

from core.models import SystemState, TankState, TelemetryLog, FaultLog

logger = logging.getLogger(__name__)

# Throttle configuration for database writes
LAST_DB_LOG_TIME = 0
LOGGING_INTERVAL = 60  # Seconds


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def _safe_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def persist_telemetry(payload: dict[str, Any]) -> bool:
    global LAST_DB_LOG_TIME
    current_time = time.time()

    if not isinstance(payload, dict):
        logger.error("Telemetry payload must be a JSON object.")
        return False

    # 1. THE SPLIT-STREAM: Instantly push to Redis
    channel_layer = get_channel_layer()
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            "telemetry_group",
            {"type": "telemetry_update", "data": payload},
        )

    # 2. Extract Data Safely
    mode = _safe_int(payload.get("mode"), 0)
    source_level = _safe_float(payload.get("source_level_percent"), 0.0)
    source_fault = _safe_bool(payload.get("source_fault"), False)
    pump_actual = _safe_bool(payload.get("pump_actual"), False)
    tanks_data = payload.get("tanks", [])

    try:
        with transaction.atomic():
            # --- THE FAULT TRAP (DEBOUNCED) ---
            current_system = SystemState.objects.filter(id=1).first()

            # A. Check for Source Faults
            if source_fault and (not current_system or not current_system.source_fault):
                FaultLog.objects.create(
                    fault_type="SOURCE_SENSOR_FAULT",
                    detected_by="EDGE",
                    snapshot=payload
                )

            # B. Check for individual Tank Faults
            if isinstance(tanks_data, list):
                for tank in tanks_data:
                    tank_id = _safe_int(tank.get("id"), 0)
                    incoming_status = _safe_int(tank.get("status"), 0)

                    if incoming_status != 0:  # 0 is OK
                        current_tank = TankState.objects.filter(system=current_system, tank_id=tank_id).first()

                        # Only log if this is a NEW fault for this specific tank
                        if not current_tank or current_tank.status != incoming_status:
                            fault_map = {1: "SENSOR_FAULT", 2: "VALVE_FAULT", 3: "COMM_LOST"}
                            fault_name = fault_map.get(incoming_status, f"UNKNOWN_FAULT_CODE_{incoming_status}")

                            FaultLog.objects.create(
                                fault_type=f"TANK_{tank_id}_{fault_name}",
                                detected_by="EDGE",
                                snapshot=payload
                            )

            # --- NORMAL STATE UPDATES ---

            # 3. Update the SINGLE "Current State" row
            state, _ = SystemState.objects.update_or_create(
                id=1,
                defaults={
                    "mode": mode,
                    "source_level_percent": source_level,
                    "source_fault": source_fault,
                    "pump_actual": pump_actual,
                }
            )

            # 4. Dynamically update ALL Tanks
            if isinstance(tanks_data, list):
                for tank in tanks_data:
                    TankState.objects.update_or_create(
                        system=state,
                        tank_id=_safe_int(tank.get("id"), 0),
                        defaults={
                            "level_percent": _safe_float(tank.get("level_percent"), 0.0),
                            "status": _safe_int(tank.get("status"), 0),
                            "valve_actual": _safe_bool(tank.get("valve_actual"), False),
                        }
                    )

            # 5. The Throttle: Log history once a minute
            if current_time - LAST_DB_LOG_TIME >= LOGGING_INTERVAL:
                TelemetryLog.objects.create(
                    mode=mode,
                    source_level_percent=source_level,
                    pump_actual=pump_actual,
                    tanks_snapshot=tanks_data,
                )
                LAST_DB_LOG_TIME = current_time

        return True
    except Exception:
        logger.exception("Failed to persist telemetry to database.")
        return False

