from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

from core.models import Command, FaultLog, SystemConfig, SystemState, TelemetryLog
from core.state_machine import evaluate_transition


def _publish_mqtt_command(_command: Command) -> bool:
    # MQTT publish is intentionally left as a stub for now.
    return False


def _create_and_validate_command(command_type: str, payload: dict, issued_by: str):
    issued_by = (issued_by or "USER").upper()

    if issued_by not in ["USER", "ADMIN"]:
        return None, Response(
            {"status": "error", "message": "issued_by must be USER or ADMIN"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        state = SystemState.objects.latest("updated_at")
    except SystemState.DoesNotExist:
        return None, Response(
            {"status": "error", "message": "No system state available"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    event = {"type": command_type, "role": issued_by, "payload": payload}
    transition = evaluate_transition(state, event)

    with transaction.atomic():
        command = Command.objects.create(
            command_type=command_type,
            payload=payload,
            issued_by=issued_by,
            status="PENDING",
            reason="Awaiting validation",
        )

        if not transition.allowed:
            command.status = "REJECTED"
            command.reason = transition.reason
            command.save(update_fields=["status", "reason"])
            return command, Response(
                {
                    "status": "rejected",
                    "command_id": command.id,
                    "reason": transition.reason,
                    "next_state": transition.next_state,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        command.status = "APPROVED"
        command.reason = transition.reason
        command.save(update_fields=["status", "reason"])

    mqtt_published = _publish_mqtt_command(command)
    return command, Response(
        {
            "status": "approved",
            "command_id": command.id,
            "reason": command.reason,
            "next_state": transition.next_state,
            "mqtt_published": mqtt_published,
            "mqtt_note": "MQTT publish not implemented yet",
        },
        status=status.HTTP_201_CREATED,
    )


def _command_endpoint(request, command_type: str):
    payload = request.data.get("payload") or {}
    issued_by = request.data.get("issued_by", "USER")
    _, response = _create_and_validate_command(command_type, payload, issued_by)
    return response


@api_view(["POST"])
def request_mode_change(request):
    return _command_endpoint(request, "REQUEST_MODE_CHANGE")


@api_view(["POST"])
def request_supply_to_tank(request):
    return _command_endpoint(request, "REQUEST_SUPPLY_TO_TANK")


@api_view(["POST"])
def request_stop(request):
    return _command_endpoint(request, "REQUEST_STOP")


@api_view(["POST"])
def enable_manual_override(request):
    return _command_endpoint(request, "ENABLE_MANUAL_OVERRIDE")


@api_view(["POST"])
def disable_manual_override(request):
    return _command_endpoint(request, "DISABLE_MANUAL_OVERRIDE")


@api_view(["POST"])
def system_shutdown(request):
    return _command_endpoint(request, "SYSTEM_SHUTDOWN")


@api_view(["POST"])
def set_priority(request):
    return _command_endpoint(request, "SET_PRIORITY")


@api_view(["POST"])
def modify_constants(request):
    payload = request.data.get("payload") or {}
    if not isinstance(payload, dict):
        return Response(
            {"status": "error", "message": "payload must be an object"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _, response = _create_and_validate_command(
        "MODIFY_CONSTANTS",
        payload,
        request.data.get("issued_by", "USER"),
    )

    if response.status_code != status.HTTP_201_CREATED:
        return response

    for key, value in payload.items():
        if not isinstance(value, (float, int)):
            return Response(
                {
                    "status": "error",
                    "message": f"Config value for '{key}' must be numeric",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        SystemConfig.objects.update_or_create(
            name=key,
            defaults={"value": float(value)},
        )

    return response


@api_view(["GET"])
def get_telemetry_history(request):
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    tanks = request.query_params.get("tanks")
    qs = TelemetryLog.objects.all().order_by("-ts")

    if start:
        qs = qs.filter(ts__gte=start)
    if end:
        qs = qs.filter(ts__lte=end)

    data = qs.values(
        "ts", "tank1_level", "tank2_level", "source_level",
        "pump_actual", "valve1_actual", "valve2_actual",
        "mode", "cloud_connection_status", "emergency_stop", "low_src_flag"
    )

    if tanks:
        tanks_set = set(tanks.split(","))
        filtered_data = []
        for row in data:
            filtered_row = {k: v for k, v in row.items() if k in tanks_set or k == "ts"}
            filtered_data.append(filtered_row)
        data = filtered_data

    return Response({
        "message": "Telemetry history fetched successfully",
        "status": "success",
        "data": list(data)
    })


@api_view(["GET"])
def get_fault_history(request):
    start = request.query_params.get("start")
    end = request.query_params.get("end")
    fault_type = request.query_params.get("fault_type")
    qs = FaultLog.objects.all().order_by("-ts")

    if start:
        qs = qs.filter(ts__gte=start)
    if end:
        qs = qs.filter(ts__lte=end)
    if fault_type:
        qs = qs.filter(fault_type=fault_type)

    data = qs.values("ts", "fault_type", "detected_by", "snapshot")
    return Response({
        "message": "Fault history fetched successfully",
        "status": "success",
        "data": list(data)
    })
