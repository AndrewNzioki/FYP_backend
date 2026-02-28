# core/models.py
from django.db import models

class SystemState(models.Model):
    MODE_CHOICES = [
        ("SYSTEM_OFF", "SYSTEM_OFF"),
        ("IDLE", "IDLE"),
        ("FILLING", "FILLING"),
        ("LOW_SUPPLY", "LOW_SUPPLY"),
        ("LOCAL_AUTONOMOUS", "LOCAL_AUTONOMOUS"),
        ("FAULT", "FAULT"),
        ("MANUAL_OVERRIDE", "MANUAL_OVERRIDE"),
    ]

    SENSOR_STATUS = [
        ("OK", "OK"),
        ("FAULT", "FAULT"),
    ]

    ACTUATOR_STATE = [
        ("ON", "ON"),
        ("OFF", "OFF"),
        ("OPEN", "OPEN"),
        ("CLOSED", "CLOSED"),
        ("FAULT", "FAULT"),
    ]

    CONNECTION_STATUS = [
        ("CONNECTED", "CONNECTED"),
        ("LOST", "LOST"),
    ]

    # ---- Core Mode ----
    mode = models.CharField(max_length=32, choices=MODE_CHOICES)

    # ---- Levels ----
    tank1_level = models.FloatField()
    tank2_level = models.FloatField()
    source_level = models.FloatField()

    # ---- Sensor Health ----
    tank1_sensor_status = models.CharField(max_length=8, choices=SENSOR_STATUS, default="OK")
    tank2_sensor_status = models.CharField(max_length=8, choices=SENSOR_STATUS, default="OK")
    source_sensor_status = models.CharField(max_length=8, choices=SENSOR_STATUS, default="OK")

    # ---- Actuator Command vs Actual ----
    pump_command = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="OFF")
    pump_actual = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="OFF")

    valve1_command = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="CLOSED")
    valve1_actual = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="CLOSED")

    valve2_command = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="CLOSED")
    valve2_actual = models.CharField(max_length=8, choices=ACTUATOR_STATE, default="CLOSED")

    # ---- Safety ----
    emergency_stop = models.BooleanField(default=False)

    # ---- Cloud ----
    cloud_connection_status = models.CharField(
        max_length=16,
        choices=CONNECTION_STATUS,
        default="CONNECTED"
    )

    updated_at = models.DateTimeField(auto_now=True)

class Command(models.Model):
    COMMAND_TYPES = [
        ("REQUEST_MODE_CHANGE", "REQUEST_MODE_CHANGE"),
        ("REQUEST_SUPPLY_TO_TANK", "REQUEST_SUPPLY_TO_TANK"),
        ("REQUEST_SUPPLY", "REQUEST_SUPPLY"),
        ("REQUEST_STOP", "REQUEST_STOP"),
        ("ENABLE_MANUAL_OVERRIDE", "ENABLE_MANUAL_OVERRIDE"),
        ("DISABLE_MANUAL_OVERRIDE", "DISABLE_MANUAL_OVERRIDE"),
        ("SYSTEM_SHUTDOWN", "SYSTEM_SHUTDOWN"),
        ("SET_PRIORITY", "SET_PRIORITY"),
        ("MODIFY_CONSTANTS", "MODIFY_CONSTANTS"),
    ]

    command_type = models.CharField(max_length=64, choices=COMMAND_TYPES)
    payload = models.JSONField()
    issued_by = models.CharField(max_length=32)  # USER / ADMIN
    status = models.CharField(
        max_length=16,
        choices=[("PENDING", "PENDING"), ("APPROVED", "APPROVED"), ("REJECTED", "REJECTED")]
    )
    reason = models.TextField(null=True)
    mqtt_topic = models.CharField(max_length=255, null=True, blank=True)
    mqtt_qos = models.PositiveSmallIntegerField(default=2)
    mqtt_published = models.BooleanField(default=False)
    mqtt_published_at = models.DateTimeField(null=True, blank=True)
    mqtt_publish_attempts = models.PositiveIntegerField(default=0)
    mqtt_last_error = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class FaultLog(models.Model):
    fault_type = models.CharField(max_length=64)
    detected_by = models.CharField(max_length=16)  # LOCAL / CLOUD
    snapshot = models.JSONField()
    ts = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ts} | {self.fault_type}"

# core/models.py

class SystemConfig(models.Model):
    name = models.CharField(max_length=64, unique=True)
    value = models.FloatField()
    description = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} = {self.value}"

class TelemetryLog(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    tank1_level = models.FloatField()
    tank2_level = models.FloatField()
    source_level = models.FloatField()
    pump_actual = models.CharField(max_length=8)
    valve1_actual = models.CharField(max_length=8)
    valve2_actual = models.CharField(max_length=8)
    mode = models.CharField(max_length=32)
    cloud_connection_status = models.CharField(max_length=16, default="CONNECTED")
    emergency_stop = models.BooleanField(default=False)
    low_src_flag = models.BooleanField(default=False)
