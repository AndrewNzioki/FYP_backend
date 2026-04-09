"""MQTT client factory and callback wiring."""

from __future__ import annotations

import random
import string

import certifi
import logging
import ssl
from typing import Any

from django.conf import settings
import paho.mqtt.client as mqtt

# 🚨 FIX: Import both handlers so we can inject them safely
from core.mqtt.handlers import TelemetryMessageHandler, CommandAckHandler

logger = logging.getLogger(__name__)

def _resolve_tls_version(version_name: str) -> int:
    mapping = {
        "TLS": ssl.PROTOCOL_TLS_CLIENT,
        "TLS_CLIENT": ssl.PROTOCOL_TLS_CLIENT,
        "TLSV1_2": ssl.PROTOCOL_TLSv1_2,
        "TLSV1_1": ssl.PROTOCOL_TLSv1_1,
        "TLSV1": ssl.PROTOCOL_TLSv1,
    }
    return mapping.get(version_name.upper(), ssl.PROTOCOL_TLS_CLIENT)

# 1.6.1 Strict Signatures
def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [MQTT] Worker successfully connected to HiveMQ Broker!")
        client.subscribe("plant/telemetry/state", qos=1)
        client.subscribe("plant/command/ack", qos=1)
    else:
        print(f"❌ [MQTT] Failed to connect, return code {rc}")

def _on_disconnect(client, userdata, rc):
    if rc == 0:
        logger.info("MQTT disconnected cleanly")
        return
    logger.warning("Unexpected MQTT disconnect rc=%s. Reconnecting...", rc)
    try:
        client.reconnect()
    except Exception:
        logger.exception("MQTT reconnect attempt failed")

def _on_message(client, userdata, msg):
    topic = msg.topic
    try:
        if topic == "plant/telemetry/state":
            userdata["telemetry_handler"].handle(client, userdata, msg)
        elif topic == "plant/command/ack":
            userdata["ack_handler"].handle(client, userdata, msg)
        else:
            logger.warning(f"Message received on unhandled topic: {topic}")
    except KeyError as e:
        logger.error(f"Missing handler in userdata for topic {topic}: {e}")
    except Exception as e:
        logger.exception(f"Crash while processing message on {topic}: {e}")

# 🚨 FIX: Accept BOTH handlers in the signature
def create_mqtt_client(
    telemetry_handler: TelemetryMessageHandler,
    ack_handler: CommandAckHandler
) -> mqtt.Client:

    random_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    client_id = f"{settings.MQTT_CLIENT_ID}-{random_id}"

    # Paho 1.6.1 Native Instantiation
    client = mqtt.Client(
        client_id=client_id,
        clean_session=settings.MQTT_CLEAN_SESSION,
        transport=settings.MQTT_TRANSPORT,
    )

    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    if settings.MQTT_TLS_ENABLED:
        client.tls_set(ca_certs=certifi.where(), tls_version=ssl.PROTOCOL_TLSv1_2)

    client.reconnect_delay_set(
        min_delay=settings.MQTT_RECONNECT_DELAY_MIN_SECONDS,
        max_delay=settings.MQTT_RECONNECT_DELAY_MAX_SECONDS,
    )
    client.enable_logger(logger)

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message

    # 🚨 FIX: Inject the exact dictionary keys the router expects
    client.user_data_set({
        "telemetry_handler": telemetry_handler,
        "ack_handler": ack_handler
    })

    return client