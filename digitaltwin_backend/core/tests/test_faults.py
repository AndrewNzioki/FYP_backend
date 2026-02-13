from core.state_machine import evaluate_transition
from core.tests.fakes import FakeSystemState


def test_sensor_fault_forces_fault_mode():
    state = FakeSystemState(
        mode="FILLING",
        tank1_sensor_status="FAULT"
    )

    event = {"type": "REQUEST_STOP"}

    result = evaluate_transition(state, event)

    assert result.next_state == "FAULT"
    assert result.allowed is True


def test_actuator_fault_forces_fault_mode():
    state = FakeSystemState(
        mode="IDLE",
        pump_command="ON",
        pump_actual="FAULT"   # actuator failed
    )

    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.next_state == "FAULT"
    assert result.allowed is True


def test_emergency_stop_forces_fault_mode():
    state = FakeSystemState(
        mode="IDLE",
        emergency_stop=True
    )

    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.next_state == "FAULT"
    assert result.allowed is True


def test_emergency_stop_overrides_everything():
    state = FakeSystemState(mode="IDLE", emergency_stop=True)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.next_state == "FAULT"
