# core/mqtt/handlers.py
import json
import logging

from core.models import Command
from core.services.state_service import persist_telemetry

logger = logging.getLogger(__name__)


class TelemetryMessageHandler:
    def handle(self, client, userdata, msg):
        try:
            raw_payload = msg.payload.decode('utf-8')
            payload = json.loads(raw_payload)

            # Offload EVERYTHING to the state service
            persist_telemetry(payload)

        except json.JSONDecodeError:
            logger.error("❌ [CRITICAL] Malformed JSON payload received from Edge.")
        except Exception as e:
            logger.error(f"❌ [CRITICAL] Error processing telemetry: {e}")

class CommandAckHandler:
    def handle(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            command_id = payload.get("command_id")
            edge_status = payload.get("status") # Expected: "ACKNOWLEDGED" or "REJECTED"
            edge_message = payload.get("message", "")

            if not command_id:
                logger.error("❌ [MQTT] ACK received without command_id.")
                return

            command = Command.objects.get(id=command_id)

            # Advance the state machine based on what the hardware said
            if edge_status == "ACKNOWLEDGED":
                command.status = Command.Status.ACKNOWLEDGED
            elif edge_status == "REJECTED":
                command.status = Command.Status.FAILED
                command.error_message = f"Hardware Rejected: {edge_message}"
            else:
                return # Ignore garbage statuses

            command.save(update_fields=["status", "error_message", "updated_at"])
            logger.info(f"✅ [MQTT] Hardware acknowledged Command {command_id}.")

            # TODO: In Step 3, we will trigger the WebSocket broadcast right here.

        except Command.DoesNotExist:
            logger.error(f"❌ [MQTT] Received ACK for unknown command_id: {command_id}")
        except json.JSONDecodeError:
            logger.error("❌ [MQTT] Malformed JSON in command ACK.")
        except Exception as e:
            logger.exception(f"❌ [MQTT] Failed to process command ACK: {e}")