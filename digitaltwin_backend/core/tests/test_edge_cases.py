# core/tests/test_edge_cases.py
from core.state_machine import evaluate_transition
from core.tests.fakes import FakeSystemState


def test_source_exactly_at_low_threshold():
    state = FakeSystemState(mode="IDLE", source_level=19)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.allowed is False


def test_low_supply_blocks_request_supply():
    state = FakeSystemState(mode="LOW_SUPPLY", source_level=19)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.allowed is False
    assert result.next_state is None


def test_cloud_loss_triggers_local_autonomous():
    state = FakeSystemState(
        mode="IDLE",
        cloud_connection_status="LOST"
    )

    event = {"type": "ANY"}

    result = evaluate_transition(state, event)

    assert result.next_state == "LOCAL_AUTONOMOUS"
