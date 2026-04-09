import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from ninja import NinjaAPI, Schema, Query
from pydantic import Field
from django.http import JsonResponse
from core.models import Command, TelemetryLog, FaultLog, SystemState, TankState
from core.tasks import publish_command_task
from ninja_jwt.authentication import JWTAuth
from ninja_jwt.controller import NinjaJWTDefaultController
from ninja_extra import NinjaExtraAPI

logger = logging.getLogger(__name__)

api = NinjaExtraAPI(title="Digital Twin SCADA API", description="Explicit Actuator Control and Telemetry")

api.register_controllers(NinjaJWTDefaultController)

ALLOWED_ISSUERS = {"USER", "ADMIN"}


# --- PYDANTIC SCHEMAS ---

class TankActionRequest(Schema):
    issued_by: str = Field("ADMIN")
    payload: Dict[str, Any] = Field(
        default={"target_tanks": [1, 2]},
        description="Provide a list of tank IDs. e.g., [1] for Tank 1, [1, 2] for both."
    )


class StandardCommandRequest(Schema):
    issued_by: str = Field("ADMIN")
    payload: Dict[str, Any] = Field(default={})


class ModifyConstantsRequest(Schema):
    issued_by: str = Field("ADMIN")
    payload: Dict[str, Any] = Field(default={"TANK_MIN": 30.0, "TANK_FULL": 95.0, "SOURCE_MIN": 20.0})


class HistoryFilter(Schema):
    start: Optional[datetime] = Field(None, description="Format: YYYY-MM-DDTHH:MM:SSZ")
    end: Optional[datetime] = Field(None, description="Format: YYYY-MM-DDTHH:MM:SSZ")
    fault_type: Optional[str] = Field(None, description="e.g., TANK_2_SENSOR_FAULT")


# --- HELPER FUNCTIONS ---

def _resolve_issuer(request, explicit_issuer: str) -> str:
    raw_issuer = str(explicit_issuer).upper()
    return "ADMIN" if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff else (
        raw_issuer if raw_issuer in ALLOWED_ISSUERS else "USER")


def _is_admin_authorized(request, issuer: str) -> bool:
    return bool(
        getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff) or issuer == "ADMIN"


def _dispatch_intent(request, intent: str, payload_data: Dict[str, Any], issued_by: str):
    issuer = _resolve_issuer(request, issued_by)
    if not _is_admin_authorized(request, issuer):
        return JsonResponse(
            {"status": "forbidden",
             "message": "Admin privileges required."},
            status=403)

    try:
        # Create the command with the new strict status and payload name
        command = Command.objects.create(
            command_type=intent,
            payload=payload_data,
            issued_by=issuer,
            status=Command.Status.QUEUED
        )

        publish_command_task.delay(str(command.id))
    except Exception:
        logger.exception("Failed to queue supervisory intent: %s", intent)
        return JsonResponse({"status": "error", "message": "Database queuing failed."}, status=503)

        # BRUTAL FIX: Return the UUID to the frontend so it can listen for updates later
    return JsonResponse({
        "status": "intent_dispatched",
        "command_id": str(command.id),  # THE CRITICAL HANDOFF
        "message": f"Command '{intent}' queued for Edge execution."
    }, status=202)


# --- EXPLICIT ACTUATOR ENDPOINTS ---

@api.post("/fill-tanks", tags=["Commands"], auth=JWTAuth())
def request_supply_to_tanks(request, data: TankActionRequest):
    targets = data.payload.get("target_tanks", [])
    if not isinstance(targets, list) or len(targets) == 0:
        return JsonResponse({"status": "error", "message": "Provide a valid list of target_tanks, e.g., [1] or [1, 2]"},
                            status=400)

    # 🚨 PRE-FLIGHT PHYSICS & ANTI-SPAM VALIDATION 🚨
    system = SystemState.objects.filter(id=1).first()
    if not system:
        return JsonResponse({"status": "error", "message": "Cannot validate: No telemetry received from Edge yet."},
                            status=503)

    if system.mode == 4:
        return JsonResponse({"status": "rejected",
                             "message": "SYSTEM REJECTED: Edge PLC is in FAULT mode. Clear faults before commanding."},
                            status=400)

    # Check for Source Fault or Empty Source
    if system.source_fault:
        return JsonResponse({"status": "rejected", "message": "SYSTEM REJECTED: Source tank sensor is faulted."},
                            status=400)
    if system.source_level_percent <= 20.0:
        return JsonResponse({"status": "rejected",
                             "message": f"SYSTEM REJECTED: Source tank is critically low ({system.source_level_percent}%). Cannot run pump."},
                            status=400)

    # Check individual tanks for faults, fullness, and duplicate commands
    for tid in targets:
        tank = TankState.objects.filter(system=system, tank_id=tid).first()
        if not tank:
            return JsonResponse(
                {"status": "error", "message": f"SYSTEM REJECTED: Tank {tid} does not exist in registry."}, status=404)

        # 1. Fault Isolation Check
        if tank.status != 0:
            return JsonResponse({"status": "rejected",
                                 "message": f"SYSTEM REJECTED: Tank {tid} is in a FAULT state. Cannot command it."},
                                status=400)

        # 2. Anti-Spam (Already Filling) Check
        if tank.valve_actual:
            return JsonResponse({"status": "rejected",
                                 "message": f"SYSTEM REJECTED: Tank {tid} is already being filled. Duplicate command ignored."},
                                status=400)

        # 3. Overflow Check
        if tank.level_percent >= 95.0:
            return JsonResponse({"status": "rejected",
                                 "message": f"SYSTEM REJECTED: Tank {tid} is already full ({tank.level_percent}%)."},
                                status=400)

    return _dispatch_intent(request, "SUPPLY_TANKS", data.payload, data.issued_by)


@api.post("/stop-filling-tanks", tags=["Commands"], auth=JWTAuth())
def stop_filling_tanks(request, data: TankActionRequest):
    targets = data.payload.get("target_tanks", [])
    if not isinstance(targets, list) or len(targets) == 0:
        return JsonResponse({"status": "error", "message": "Provide a valid list of target_tanks, e.g., [1] or [1, 2]"},
                            status=400)
    return _dispatch_intent(request, "STOP_SUPPLY_TANKS", data.payload, data.issued_by)


@api.post("/emergency-stop", tags=["Commands"], auth=JWTAuth())
def emergency_stop(request, data: StandardCommandRequest):
    return _dispatch_intent(request, "EMERGENCY_STOP", data.payload, data.issued_by)


@api.post("/clear-fault", tags=["Commands"], auth=JWTAuth())
def clear_fault(request, data: StandardCommandRequest):
    """Attempts to remove the system from FAULT mode (Only works if hardware is physically healthy)."""
    return _dispatch_intent(request, "CLEAR_FAULT", data.payload, data.issued_by)


@api.post("/modify-constants", tags=["Commands"], auth=JWTAuth())
def modify_constants(request, data: ModifyConstantsRequest):
    return _dispatch_intent(request, "MODIFY_CONSTANTS", data.payload, data.issued_by)


# --- HISTORY ENDPOINTS ---
@api.get("/telemetry-history", tags=["History"], auth=JWTAuth())
def get_telemetry_history(request, filters: HistoryFilter = Query(...)):
    qs = TelemetryLog.objects.all().order_by("-ts")
    if filters.start: qs = qs.filter(ts__gte=filters.start)
    if filters.end: qs = qs.filter(ts__lte=filters.end)
    return {"status": "success",
            "data": list(qs.values("ts", "mode", "source_level_percent", "pump_actual", "tanks_snapshot"))}


@api.get("/fault-history", tags=["History"], auth=JWTAuth())
def get_fault_history(request, filters: HistoryFilter = Query(...)):
    qs = FaultLog.objects.all().order_by("-ts")
    if filters.start: qs = qs.filter(ts__gte=filters.start)
    if filters.end: qs = qs.filter(ts__lte=filters.end)
    if filters.fault_type: qs = qs.filter(fault_type=filters.fault_type)
    return {"status": "success", "data": list(qs.values("ts", "fault_type", "detected_by", "snapshot"))}
