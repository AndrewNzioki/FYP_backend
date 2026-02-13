from core.faults import detect_fault
from core.utils import record_fault, record_telemetry

def update_system_state(state):
    """
    Centralized handler for any SystemState update.
    1. Records telemetry.
    2. Detects and records faults.
    3. Returns current fault status.
    """
    # --- Log telemetry ---
    record_telemetry(state)

    # --- Detect faults ---
    fault, reason = detect_fault(state)
    if fault:
        record_fault(state, reason)

    return fault, reason
