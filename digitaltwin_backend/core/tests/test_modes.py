# core/tests/test_modes.py
import pytest
from core.state_machine import evaluate_transition
from core.tests.fakes import FakeSystemState


def test_idle_to_filling_nominal():
    state = FakeSystemState(mode="IDLE", source_level=80)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.allowed is True
    assert result.next_state == "FILLING"


@pytest.mark.parametrize(
    "mode,source,expected",
    [
        ("IDLE", 80, True),
        ("IDLE", 15, False),
        ("FILLING", 80, False),
        ("LOW_SUPPLY", 19, False),
    ]
)
def test_request_supply_matrix(mode, source, expected):
    state = FakeSystemState(mode=mode, source_level=source)
    event = {"type": "REQUEST_SUPPLY"}

    result = evaluate_transition(state, event)

    assert result.allowed is expected
