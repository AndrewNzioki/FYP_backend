# core/mqtt/handlers.py
import json
import logging
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