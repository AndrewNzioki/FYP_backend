from digitaltwin_backend.core.models import Command, SystemState
from digitaltwin_backend.core.rules import validate_command


def process_command(command_id):
    command = Command.objects.get(id=command_id)
    state = SystemState.objects.latest("updated_at")

    allowed, reason = validate_command(state, command)

    if not allowed:
        command.status = "REJECTED"
        command.reason = reason
        command.save()
        return

    command.status = "APPROVED"
    command.reason = reason
    command.save()
