"""State and telemetry persistence service.

This module centralizes database writes triggered by incoming MQTT telemetry.
It keeps DB operations transaction-safe and isolates message handlers from ORM details.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from core.faults import detect_fault
from core.models import FaultLog, SystemState, TelemetryLog
from core.utils import get_config_value

logger = logging.getLogger(__name__)

_MODE_VALUES = {choice for choice, _ in SystemState.MODE_CHOICES}
_SENSOR_VALUES = {choice for choice, _ in SystemState.SENSOR_STATUS}
_ACTUATOR_VALUES = {choice for choice, _ in SystemState.ACTUATOR_STATE}
_CONNECTION_VALUES = {choice for choice, _ in SystemState.CONNECTION_STATUS}


def _safe_float(value: Any, default: float) -> float:
    """Return a float value if possible; otherwise use default."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value: Any, default: bool) -> bool:
    """Return a bool for common boolean-like payload values."""
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


def _safe_choice(value: Any, allowed: set[str], default: str, field_name: str) -> str:
    """Validate a model choice value, logging when payload values are invalid."""
    candidate = str(value).upper() if value is not None else default
    if candidate in allowed:
        return candidate

    logger.warning("Invalid telemetry value for %s: %r. Using %s.", field_name, value, default)
    return default


def _build_fault_snapshot(state: SystemState) -> dict[str, Any]:
    """Build the snapshot payload used by FaultLog."""
    return {
        "tank1_level": state.tank1_level,
        "tank2_level": state.tank2_level,
        "source_level": state.source_level,
        "pump_actual": state.pump_actual,
        "valve1_actual": state.valve1_actual,
        "valve2_actual": state.valve2_actual,
        "mode": state.mode,
        "cloud_connection_status": state.cloud_connection_status,
        "emergency_stop": state.emergency_stop,
    }


def _get_or_create_state_locked() -> SystemState:
    """Fetch the latest state row with a lock, creating one when missing."""
    state = SystemState.objects.select_for_update().order_by("-updated_at").first()
    if state:
        return state

    logger.info("No SystemState row found. Creating an initial default row.")
    return SystemState.objects.create(
        mode="IDLE",
        tank1_level=0.0,
        tank2_level=0.0,
        source_level=0.0,
        tank1_sensor_status="OK",
        tank2_sensor_status="OK",
        source_sensor_status="OK",
        pump_command="OFF",
        pump_actual="OFF",
        valve1_command="CLOSED",
        valve1_actual="CLOSED",
        valve2_command="CLOSED",
        valve2_actual="CLOSED",
        emergency_stop=False,
        cloud_connection_status="CONNECTED",
    )


def persist_telemetry(topic: str, payload: dict[str, Any]) -> bool:
    """Persist telemetry by updating current state, recording telemetry, and fault detection.

    Returns True when telemetry was persisted successfully.
    """
    if not isinstance(payload, dict):
        logger.error("Telemetry payload must be a JSON object. topic=%s payload=%r", topic, payload)
        return False

    try:
        with transaction.atomic():
            state = _get_or_create_state_locked()

            state.mode = _safe_choice(payload.get("mode"), _MODE_VALUES, state.mode, "mode")

            state.tank1_level = _safe_float(payload.get("tank1_level"), state.tank1_level)
            state.tank2_level = _safe_float(payload.get("tank2_level"), state.tank2_level)
            state.source_level = _safe_float(payload.get("source_level"), state.source_level)

            state.tank1_sensor_status = _safe_choice(
                payload.get("tank1_sensor_status"), _SENSOR_VALUES, state.tank1_sensor_status, "tank1_sensor_status"
            )
            state.tank2_sensor_status = _safe_choice(
                payload.get("tank2_sensor_status"), _SENSOR_VALUES, state.tank2_sensor_status, "tank2_sensor_status"
            )
            state.source_sensor_status = _safe_choice(
                payload.get("source_sensor_status"), _SENSOR_VALUES, state.source_sensor_status, "source_sensor_status"
            )

            state.pump_command = _safe_choice(payload.get("pump_command"), _ACTUATOR_VALUES, state.pump_command, "pump_command")
            state.pump_actual = _safe_choice(payload.get("pump_actual"), _ACTUATOR_VALUES, state.pump_actual, "pump_actual")
            state.valve1_command = _safe_choice(
                payload.get("valve1_command"), _ACTUATOR_VALUES, state.valve1_command, "valve1_command"
            )
            state.valve1_actual = _safe_choice(
                payload.get("valve1_actual"), _ACTUATOR_VALUES, state.valve1_actual, "valve1_actual"
            )
            state.valve2_command = _safe_choice(
                payload.get("valve2_command"), _ACTUATOR_VALUES, state.valve2_command, "valve2_command"
            )
            state.valve2_actual = _safe_choice(
                payload.get("valve2_actual"), _ACTUATOR_VALUES, state.valve2_actual, "valve2_actual"
            )
            state.cloud_connection_status = _safe_choice(
                payload.get("cloud_connection_status"),
                _CONNECTION_VALUES,
                state.cloud_connection_status,
                "cloud_connection_status",
            )
            state.emergency_stop = _safe_bool(payload.get("emergency_stop"), state.emergency_stop)

            state.save()

            low_threshold = get_config_value("LOW_THRESHOLD", 20)
            TelemetryLog.objects.create(
                tank1_level=state.tank1_level,
                tank2_level=state.tank2_level,
                source_level=state.source_level,
                pump_actual=state.pump_actual,
                valve1_actual=state.valve1_actual,
                valve2_actual=state.valve2_actual,
                mode=state.mode,
                cloud_connection_status=state.cloud_connection_status,
                emergency_stop=state.emergency_stop,
                low_src_flag=state.source_level <= low_threshold,
            )

            fault, reason = detect_fault(state)
            if fault and reason:
                snapshot = _build_fault_snapshot(state)
                last_fault = FaultLog.objects.order_by("-ts").first()
                if not last_fault or last_fault.fault_type != reason or last_fault.snapshot != snapshot:
                    FaultLog.objects.create(
                        fault_type=reason,
                        detected_by="CLOUD",
                        snapshot=snapshot,
                    )
                    logger.warning("Fault detected from telemetry topic=%s fault=%s", topic, reason)

            return True
    except Exception:
        logger.exception("Failed to persist telemetry for topic=%s", topic)
        return False

