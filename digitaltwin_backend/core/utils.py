# core/utils.py

from core.models import SystemConfig
from core.models import FaultLog
from core.models import TelemetryLog

def get_config_value(name: str, default=None) -> float:
    try:
        return SystemConfig.objects.get(name=name).value
    except SystemConfig.DoesNotExist:
        return default

def record_fault(state, fault_type, detected_by="LOCAL"):

    FaultLog.objects.create(
        fault_type=fault_type,
        detected_by=detected_by,
        snapshot={
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
    )

def record_telemetry(state):

    LOW_THRESHOLD = get_config_value("LOW_THRESHOLD", 20)

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
        low_src_flag=state.source_level <= LOW_THRESHOLD,
    )
