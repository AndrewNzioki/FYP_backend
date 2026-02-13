# core/tests/test_commands.py
import json
import pytest
from django.test import Client

from core.models import Command, SystemState
from core.state_machine import evaluate_transition
from core.tests.fakes import FakeSystemState


def test_reject_supply_when_source_low():
    state = FakeSystemState(mode="IDLE", source_level=10)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.allowed is False
    assert result.next_state is None


def test_manual_override_admin_only():
    state = FakeSystemState(mode="IDLE")

    user_event = {"type": "ENABLE_MANUAL_OVERRIDE", "role": "USER"}
    admin_event = {"type": "ENABLE_MANUAL_OVERRIDE", "role": "ADMIN"}

    assert evaluate_transition(state, user_event).allowed is False

    result = evaluate_transition(state, admin_event)
    assert result.allowed is True
    assert result.next_state == "MANUAL_OVERRIDE"


@pytest.fixture
def api_client():
    return Client()


@pytest.fixture
def system_state(db):
    return SystemState.objects.create(
        mode="IDLE",
        tank1_level=40,
        tank2_level=45,
        source_level=80,
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


def test_request_supply_to_tank_endpoint_approved(api_client, system_state):
    response = api_client.post(
        "/api/commands/request-supply-to-tank/",
        data=json.dumps({"issued_by": "USER", "payload": {"tank": 1}}),
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "approved"

    command = Command.objects.get(id=body["command_id"])
    assert command.command_type == "REQUEST_SUPPLY_TO_TANK"
    assert command.issued_by == "USER"
    assert command.status == "APPROVED"
    assert command.reason


def test_request_supply_to_tank_rejected_records_reason(api_client, system_state):
    system_state.source_level = 10
    system_state.save(update_fields=["source_level"])

    response = api_client.post(
        "/api/commands/request-supply-to-tank/",
        data=json.dumps({"issued_by": "USER", "payload": {"tank": 2}}),
        content_type="application/json",
    )

    assert response.status_code == 400
    body = response.json()
    assert body["status"] == "rejected"
    assert "reason" in body

    command = Command.objects.get(id=body["command_id"])
    assert command.status == "REJECTED"
    assert command.reason == body["reason"]


def test_disable_manual_override_admin_only(api_client, system_state):
    system_state.mode = "MANUAL_OVERRIDE"
    system_state.save(update_fields=["mode"])

    user_response = api_client.post(
        "/api/commands/disable-manual-override/",
        data=json.dumps({"issued_by": "USER", "payload": {}}),
        content_type="application/json",
    )
    assert user_response.status_code == 400
    assert user_response.json()["reason"] == "Admin only"

    admin_response = api_client.post(
        "/api/commands/disable-manual-override/",
        data=json.dumps({"issued_by": "ADMIN", "payload": {}}),
        content_type="application/json",
    )
    assert admin_response.status_code == 201
    assert admin_response.json()["status"] == "approved"
