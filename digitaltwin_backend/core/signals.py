from django.db.models.signals import post_save
from django.dispatch import receiver
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from core.models import Command


@receiver(post_save, sender=Command)
def broadcast_command_update(sender, instance: Command, **kwargs):
    """
    Automatically pushes command state changes to the Compose Multiplatform UI
    the millisecond they hit the database.
    """
    channel_layer = get_channel_layer()
    if channel_layer:
        payload = {
            "command_id": str(instance.id),
            "command_type": instance.command_type,
            "status": instance.status,
            "error_message": instance.error_message,
            "updated_at": instance.updated_at.isoformat()
        }

        # Fire it down the pipe
        async_to_sync(channel_layer.group_send)(
            "command_updates",
            {
                "type": "command_update",  # Matches the consumer method
                "data": payload
            }
        )