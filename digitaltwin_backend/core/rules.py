from core.state_machine import evaluate_transition


def validate_command(system_state, command):

    if system_state.mode == "FAULT":
        return False, "System in FAULT"

    result = evaluate_transition(system_state, {
        "type": command.command_type,
        "role": command.issued_by,
        "payload": command.payload
    })

    if not result.allowed:
        return False, result.reason

    return True, "Approved"

