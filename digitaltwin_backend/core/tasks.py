import json
import logging
from celery import shared_task
import paho.mqtt.publish as publish
from django.conf import settings
from core.models import Command

logger = logging.getLogger(__name__)


@shared_task
def publish_command_task(command_id_str: str):
    """Instantly publishes a queued command to the MQTT broker."""
    try:
        # 1. Lock the command to prevent double-publishing
        command = Command.objects.get(id=command_id_str, status=Command.Status.QUEUED)

        # 2. Build the exact payload the ESP32 expects
        payload = {
            "command_id": str(command.id),
            "command_type": command.command_type,
            "target_payload": command.payload,
            "issued_by": command.issued_by
        }

        # 3. Publish synchronously within the async worker
        publish.single(
            topic=settings.MQTT_COMMAND_TOPIC,  # e.g., 'plant/command/inbound'
            payload=json.dumps(payload),
            qos=1,  # QoS 1 guarantees delivery to the broker
            hostname=settings.MQTT_BROKER_HOST,
            port=settings.MQTT_BROKER_PORT,
            client_id=f"celery_pub_{command.id}",
            auth={'username': settings.MQTT_USERNAME,
                  'password': settings.MQTT_PASSWORD} if settings.MQTT_USERNAME else None
        )

        # 4. Advance the state machine
        command.status = Command.Status.PUBLISHED
        command.save(update_fields=["status", "updated_at"])

        logger.info(f"✅ [CELERY] Published Command {command.id} to broker.")

    except Command.DoesNotExist:
        logger.error(f"❌ [CELERY] Command {command_id_str} not found or not QUEUED.")
    except Exception as e:
        logger.exception(f"❌ [CELERY] Failed to publish Command {command_id_str}: {e}")
        # Mark as failed so the UI doesn't hang forever
        Command.objects.filter(id=command_id_str).update(
            status=Command.Status.FAILED,
            error_message=f"MQTT Publish Failed: {str(e)}"
        )