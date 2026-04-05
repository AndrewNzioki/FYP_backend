from django.db import models


class SystemState(models.Model):
    class EdgeMode(models.IntegerChoices):
        IDLE = 0, "IDLE"
        HYDRAULIC_TRANSITION = 1, "HYDRAULIC_TRANSITION"
        FILLING = 2, "FILLING"
        LOW_SUPPLY = 3, "LOW_SUPPLY"
        FAULT = 4, "FAULT"

    MODE_CHOICES = EdgeMode.choices

    mode = models.PositiveSmallIntegerField(
        choices=MODE_CHOICES,
        default=EdgeMode.IDLE,
    )
    source_level_percent = models.FloatField(default=0.0)

    source_fault = models.BooleanField(default=False)
    pump_actual = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

class TankState(models.Model):
    class NodeStatus(models.IntegerChoices):
        OK = 0, "OK"
        SENSOR_FAULT = 1, "SENSOR_FAULT"
        VALVE_FAULT = 2, "VALVE_FAULT"
        COMM_LOST = 3, "COMM_LOST"

    # Links this tank reading to the overarching system state
    system = models.ForeignKey(
        SystemState,
        related_name="tanks",
        on_delete=models.CASCADE
    )
    tank_id = models.PositiveSmallIntegerField()
    level_percent = models.FloatField(default=0.0)
    status = models.PositiveSmallIntegerField(
        choices=NodeStatus.choices,
        default=NodeStatus.OK
    )
    valve_actual = models.BooleanField(default=False)


class Command(models.Model):
    COMMAND_TYPES = [
        ("REQUEST_MODE_CHANGE", "REQUEST_MODE_CHANGE"),
        ("REQUEST_SUPPLY_TO_TANK", "REQUEST_SUPPLY_TO_TANK"),
        ("REQUEST_STOP", "REQUEST_STOP"),
        ("SYSTEM_SHUTDOWN", "SYSTEM_SHUTDOWN"),
        ("MODIFY_CONSTANTS", "MODIFY_CONSTANTS"),
    ]

    command_type = models.CharField(max_length=64, choices=COMMAND_TYPES)
    payload = models.JSONField()
    issued_by = models.CharField(max_length=32)
    status = models.CharField(
        max_length=16,
        choices=[("PENDING", "PENDING"), ("APPROVED", "APPROVED"), ("REJECTED", "REJECTED")]
    )
    reason = models.TextField(null=True)

    # 🚨 RESTORED MQTT TRACKING FIELDS 🚨
    mqtt_topic = models.CharField(max_length=255, null=True, blank=True)
    mqtt_qos = models.PositiveSmallIntegerField(default=2)
    mqtt_published = models.BooleanField(default=False)
    mqtt_published_at = models.DateTimeField(null=True, blank=True)
    mqtt_publish_attempts = models.PositiveIntegerField(default=0)
    mqtt_last_error = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

class TelemetryLog(models.Model):
    ts = models.DateTimeField(auto_now_add=True)
    mode = models.PositiveSmallIntegerField(choices=SystemState.EdgeMode.choices)
    source_level_percent = models.FloatField()
    pump_actual = models.BooleanField()
    tanks_snapshot = models.JSONField()

class FaultLog(models.Model):
    fault_type = models.CharField(max_length=64)
    detected_by = models.CharField(max_length=16, default="EDGE")
    snapshot = models.JSONField() # Stores the entire telemetry payload at the moment of failure
    ts = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.ts} | {self.fault_type}"

class SystemConfig(models.Model):
    name = models.CharField(max_length=64, unique=True)
    value = models.FloatField()
    description = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)