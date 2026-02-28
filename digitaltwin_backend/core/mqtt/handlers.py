"""MQTT message handlers for telemetry topics."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from typing import Any

from django.conf import settings
from paho.mqtt.client import MQTTMessage

from core.services.state_service import persist_telemetry

logger = logging.getLogger(__name__)


class TelemetryMessageHandler:
    """Handle telemetry MQTT messages and dispatch them to the service layer.

    The handler keeps a small in-memory cache of dedupe keys to avoid writing the
    same QoS replay repeatedly (for duplicate deliveries or repeated message IDs).
    """

    def __init__(self, max_seen_messages: int = 2048) -> None:
        self.max_seen_messages = max_seen_messages
        self._seen_lock = threading.Lock()
        self._seen_keys: OrderedDict[str, None] = OrderedDict()
        self._telemetry_topics = {
            settings.MQTT_TELEMETRY_STATE_TOPIC,
            settings.MQTT_TELEMETRY_HEALTH_TOPIC,
        }

    def handle(self, msg: MQTTMessage) -> None:
        """Process a single MQTT message safely."""
        topic = msg.topic
        if topic not in self._telemetry_topics:
            logger.debug("Ignoring unsupported MQTT topic: %s", topic)
            return

        payload = self._decode_payload(msg.payload)
        if payload is None:
            return

        dedupe_key, has_explicit_message_id = self._build_dedupe_key(topic, payload)
        is_duplicate_replay = (msg.dup or has_explicit_message_id) and self._already_seen(dedupe_key)
        if is_duplicate_replay:
            logger.info("Skipping duplicate telemetry replay topic=%s", topic)
            return

        if persist_telemetry(topic=topic, payload=payload):
            self._mark_seen(dedupe_key)

    def _decode_payload(self, payload_bytes: bytes) -> dict[str, Any] | None:
        """Decode telemetry payload and enforce object JSON schema."""
        try:
            decoded = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.exception("Failed to decode telemetry payload")
            return None

        if not isinstance(decoded, dict):
            logger.error("Telemetry payload must be a JSON object, got %s", type(decoded).__name__)
            return None

        return decoded

    def _build_dedupe_key(self, topic: str, payload: dict[str, Any]) -> tuple[str, bool]:
        """Build a stable dedupe key from explicit message ID or canonical payload hash."""
        explicit_id = payload.get("message_id") or payload.get("telemetry_id")
        if explicit_id is not None:
            return f"{topic}:{explicit_id}", True

        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(f"{topic}|{canonical}".encode("utf-8")).hexdigest()
        return digest, False

    def _already_seen(self, dedupe_key: str) -> bool:
        """Check whether a message dedupe key exists in the recent cache."""
        with self._seen_lock:
            return dedupe_key in self._seen_keys

    def _mark_seen(self, dedupe_key: str) -> None:
        """Insert key into recency cache with bounded memory use."""
        with self._seen_lock:
            self._seen_keys[dedupe_key] = None
            self._seen_keys.move_to_end(dedupe_key)
            while len(self._seen_keys) > self.max_seen_messages:
                self._seen_keys.popitem(last=False)

