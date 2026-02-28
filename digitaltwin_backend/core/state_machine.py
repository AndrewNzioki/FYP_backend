from __future__ import annotations

from dataclasses import dataclass
from core.faults import detect_fault
from core.utils import get_config_value


@dataclass
class TransitionResult:
    allowed: bool
    next_state: str | None
    reason: str


def evaluate_transition(state, event) -> TransitionResult:
    event_type = event.get("type")
    role = event.get("role", "USER")
    payload = event.get("payload") or {}

    # Pull thresholds dynamically from config
    low_threshold = get_config_value("LOW_THRESHOLD", 20)
    critical_threshold = get_config_value("CRITICAL_THRESHOLD", 15)
    recovery_threshold = get_config_value("RECOVERY_THRESHOLD", 30)

    # Global fault dominance
    fault, reason = detect_fault(state)
    if fault or state.mode == "FAULT":
        # We only allow admins to shut the system down if it's in a fault.
        if event_type == "SYSTEM_SHUTDOWN" and role == "ADMIN":
            return TransitionResult(True, "SYSTEM_OFF", "Emergency shutdown approved.")

        # EVERYTHING else is rejected.
        return TransitionResult(
            allowed=False,
            next_state=None,
            reason=f"Command REJECTED. System is locked in FAULT: {reason or 'Unknown Fault'}"
        )

    # Cloud loss handling
    if state.cloud_connection_status == "LOST" and state.mode in ["IDLE", "FILLING"]:
        return TransitionResult(True, "LOCAL_AUTONOMOUS", "Cloud lost")

    # Configuration commands do not force mode transitions.
    if event_type in ["SET_PRIORITY", "MODIFY_CONSTANTS"]:
        return TransitionResult(True, state.mode, f"{event_type} accepted")

    if event_type == "SYSTEM_SHUTDOWN":
        if role != "ADMIN":
            return TransitionResult(False, None, "Admin only")
        return TransitionResult(True, "SYSTEM_OFF", "Shutdown approved")

    if state.mode == "IDLE":
        if event_type in ["REQUEST_SUPPLY", "REQUEST_SUPPLY_TO_TANK"]:
            target_tank = payload.get("tank")
            if target_tank not in [None, 1, 2]:
                return TransitionResult(False, None, "Invalid tank target")
            if state.source_level < low_threshold:
                return TransitionResult(False, None, "Source below LOW threshold")
            return TransitionResult(True, "FILLING", "Supply allowed")

        if event_type == "ENABLE_MANUAL_OVERRIDE":
            if role != "ADMIN":
                return TransitionResult(False, None, "Admin only")
            return TransitionResult(True, "MANUAL_OVERRIDE", "Manual override enabled")

        if event_type == "REQUEST_MODE_CHANGE":
            target_mode = payload.get("target_mode")

            if target_mode == "FILLING":
                if state.source_level < low_threshold:
                    return TransitionResult(False, None, "Source below LOW threshold")
                return TransitionResult(True, "FILLING", "Mode change to FILLING allowed")

            if target_mode == "MANUAL_OVERRIDE":
                if role != "ADMIN":
                    return TransitionResult(False, None, "Admin only")
                return TransitionResult(True, "MANUAL_OVERRIDE", "Mode change to MANUAL_OVERRIDE allowed")

            if target_mode == "SYSTEM_OFF":
                if role != "ADMIN":
                    return TransitionResult(False, None, "Admin only")
                return TransitionResult(True, "SYSTEM_OFF", "Mode change to SYSTEM_OFF allowed")

            return TransitionResult(False, None, "Unsupported target mode for REQUEST_MODE_CHANGE")

    if state.mode == "FILLING":
        if event_type == "REQUEST_STOP":
            return TransitionResult(True, "IDLE", "Stop requested")

        if event_type == "REQUEST_MODE_CHANGE" and payload.get("target_mode") == "IDLE":
            return TransitionResult(True, "IDLE", "Mode change to IDLE allowed")

        if state.source_level <= critical_threshold:
            return TransitionResult(True, "LOW_SUPPLY", "Source critically low")

    if state.mode == "LOW_SUPPLY":
        if state.source_level >= recovery_threshold:
            return TransitionResult(True, "FILLING", "Source recovered")
        if event_type == "REQUEST_STOP":
            return TransitionResult(True, "IDLE", "Stopped by request")

    if state.mode == "LOCAL_AUTONOMOUS":
        if state.cloud_connection_status == "CONNECTED":
            return TransitionResult(True, "IDLE", "Cloud restored")
        if state.source_level <= critical_threshold:
            return TransitionResult(True, "LOW_SUPPLY", "Critical level in local mode")

    if state.mode == "MANUAL_OVERRIDE":
        if event_type == "DISABLE_MANUAL_OVERRIDE":
            if role != "ADMIN":
                return TransitionResult(False, None, "Admin only")
            return TransitionResult(True, "IDLE", "Manual override disabled")

    return TransitionResult(False, None, "No valid transition")
