"""MQTT command publisher for approved backend commands."""

from __future__ import annotations

import json
import logging
from typing import Any

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone
import paho.mqtt.client as mqtt

from core.models import Command

logger = logging.getLogger(__name__)


class CommandPublisher:
    """Publish approved commands with QoS2 and mark DB state after broker acknowledgement."""

    def __init__(self, client: mqtt.Client) -> None:
        self.client = client

    def publish_approved_commands(self, batch_size: int | None = None) -> int:
        """Publish pending approved commands and return number successfully published."""
        close_old_connections()

        limit = batch_size or settings.MQTT_COMMAND_BATCH_SIZE
        command_ids = list(
            Command.objects.filter(status="APPROVED", mqtt_published=False)
            .order_by("created_at")
            .values_list("id", flat=True)[:limit]
        )

        published_count = 0
        for command_id in command_ids:
            if self._publish_single_command(command_id):
                published_count += 1
        return published_count

    def _publish_single_command(self, command_id: int) -> bool:
        """Publish one command and update persistence only after PUBACK/PUBCOMP."""
        topic = settings.MQTT_COMMAND_TOPIC
        qos = settings.MQTT_COMMAND_QOS

        with transaction.atomic():
            command = (
                Command.objects.select_for_update()
                .filter(id=command_id, status="APPROVED", mqtt_published=False)
                .first()
            )
            if not command:
                return False

            command.mqtt_publish_attempts += 1
            command.mqtt_topic = topic
            command.mqtt_qos = qos
            command.save(update_fields=["mqtt_publish_attempts", "mqtt_topic", "mqtt_qos"])

            payload = self._serialize_command(command)

        try:
            info = self.client.publish(topic=topic, payload=payload, qos=qos, retain=False)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed with rc={info.rc}")

            info.wait_for_publish(timeout=settings.MQTT_PUBLISH_ACK_TIMEOUT_SECONDS)
            if not info.is_published():
                raise TimeoutError("Timed out waiting for MQTT publish acknowledgement")

            with transaction.atomic():
                updated = Command.objects.filter(id=command_id, mqtt_published=False).update(
                    mqtt_published=True,
                    mqtt_published_at=timezone.now(),
                    mqtt_last_error=None,
                )

            if updated:
                logger.info("Published command_id=%s topic=%s qos=%s", command_id, topic, qos)
            return bool(updated)
        except Exception as exc:
            logger.exception("Failed publishing command_id=%s", command_id)
            Command.objects.filter(id=command_id).update(mqtt_last_error=str(exc)[:2000])
            return False

    @staticmethod
    def _serialize_command(command: Command) -> str:
        """Serialize command record to edge-facing MQTT payload."""
        payload: dict[str, Any] = {
            "command_id": command.id,
            "command_type": command.command_type,
            "payload": command.payload,
            "issued_by": command.issued_by,
            "created_at": command.created_at.isoformat(),
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)

