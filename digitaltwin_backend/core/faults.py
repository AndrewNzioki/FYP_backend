# core/faults.py
from core.utils import get_config_value

MIN_SOURCE_OPERATIONAL = get_config_value("MIN_SOURCE_OPERATIONAL", 5)

def detect_fault(state):
    # Emergency stop always wins
    if state.emergency_stop:
        return True, "EMERGENCY_STOP"

    # Sensor faults
    if (
        state.tank1_sensor_status == "FAULT"
        or state.tank2_sensor_status == "FAULT"
        or state.source_sensor_status == "FAULT"
    ):
        return True, "SENSOR_FAULT"

    # Actuator mismatch
    if state.pump_command != state.pump_actual:
        return True, "PUMP_MISMATCH"

    if state.valve1_command != state.valve1_actual:
        return True, "VALVE1_MISMATCH"

    if state.valve2_command != state.valve2_actual:
        return True, "VALVE2_MISMATCH"

    # Impossible physical condition
    if state.source_level < 0:
        return True, "INVALID_SOURCE_READING"

    if state.source_level <= MIN_SOURCE_OPERATIONAL:
        return True, "CRITICAL_SOURCE_EMPTY"

    return False, None
