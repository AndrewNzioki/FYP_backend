# core/tests/fakes.py
from dataclasses import dataclass
from datetime import datetime


@dataclass
class FakeSystemState:
    # ---- Core Mode ----
    mode: str

    # ---- Levels ----
    tank1_level: float = 50.0
    tank2_level: float = 50.0
    source_level: float = 50.0

    # ---- Sensor Health ----
    tank1_sensor_status: str = "OK"
    tank2_sensor_status: str = "OK"
    source_sensor_status: str = "OK"

    # ---- Actuator Command vs Actual ----
    pump_command: str = "OFF"
    pump_actual: str = "OFF"

    valve1_command: str = "CLOSED"
    valve1_actual: str = "CLOSED"

    valve2_command: str = "CLOSED"
    valve2_actual: str = "CLOSED"

    # ---- Safety ----
    emergency_stop: bool = False

    # ---- Cloud ----
    cloud_connection_status: str = "CONNECTED"

    # ---- Timestamp (to mirror model) ----
    updated_at: datetime = datetime.now()
