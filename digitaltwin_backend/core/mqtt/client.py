"""MQTT client factory and callback wiring."""

from __future__ import annotations

import logging
import ssl
from typing import Any

from django.conf import settings
import paho.mqtt.client as mqtt

from core.mqtt.handlers import TelemetryMessageHandler

logger = logging.getLogger(__name__)


def _resolve_tls_version(version_name: str) -> int:
    """Map env-provided TLS version strings to ssl constants."""
    mapping = {
        "TLS": ssl.PROTOCOL_TLS_CLIENT,
        "TLS_CLIENT": ssl.PROTOCOL_TLS_CLIENT,
        "TLSV1_2": ssl.PROTOCOL_TLSv1_2,
        "TLSV1_1": ssl.PROTOCOL_TLSv1_1,
        "TLSV1": ssl.PROTOCOL_TLSv1,
    }
    return mapping.get(version_name.upper(), ssl.PROTOCOL_TLS_CLIENT)


def create_mqtt_client(handler: TelemetryMessageHandler) -> mqtt.Client:
    """Create and configure MQTT client with callbacks and secure options."""
    client = mqtt.Client(
        client_id=settings.MQTT_CLIENT_ID,
        protocol=mqtt.MQTTv311,
        clean_session=settings.MQTT_CLEAN_SESSION,
        transport=settings.MQTT_TRANSPORT,
    )

    if settings.MQTT_USERNAME:
        client.username_pw_set(settings.MQTT_USERNAME, settings.MQTT_PASSWORD)

    if settings.MQTT_TLS_ENABLED:
        tls_version = _resolve_tls_version(settings.MQTT_TLS_VERSION)
        client.tls_set(
            ca_certs=settings.MQTT_TLS_CA_CERT or None,
            certfile=settings.MQTT_TLS_CERTFILE or None,
            keyfile=settings.MQTT_TLS_KEYFILE or None,
            tls_version=tls_version,
        )
        client.tls_insecure_set(settings.MQTT_TLS_INSECURE)

    client.reconnect_delay_set(
        min_delay=settings.MQTT_RECONNECT_DELAY_MIN_SECONDS,
        max_delay=settings.MQTT_RECONNECT_DELAY_MAX_SECONDS,
    )
    client.enable_logger(logger)

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.user_data_set({"handler": handler})

    return client


def _on_connect(client: mqtt.Client, userdata: dict[str, Any], flags: dict[str, Any], rc: int) -> None:
    """Subscribe to telemetry topics once connected."""
    if rc != 0:
        logger.error("MQTT connection failed with rc=%s", rc)
        return

    telemetry_qos = settings.MQTT_TELEMETRY_QOS
    for topic in (settings.MQTT_TELEMETRY_STATE_TOPIC, settings.MQTT_TELEMETRY_HEALTH_TOPIC):
        result, mid = client.subscribe(topic, qos=telemetry_qos)
        if result != mqtt.MQTT_ERR_SUCCESS:
            logger.error("Failed subscribing to topic=%s result=%s", topic, result)
        else:
            logger.info("Subscribed topic=%s qos=%s mid=%s", topic, telemetry_qos, mid)

    logger.info("MQTT connected rc=%s session_present=%s", rc, flags.get("session present"))


def _on_disconnect(client: mqtt.Client, userdata: dict[str, Any], rc: int) -> None:
    """Log disconnects and attempt explicit reconnect when unexpected."""
    if rc == 0:
        logger.info("MQTT disconnected cleanly")
        return

    logger.warning("Unexpected MQTT disconnect rc=%s. Reconnect will be attempted.", rc)
    try:
        client.reconnect()
    except Exception:
        logger.exception("MQTT reconnect attempt failed")


def _on_message(client: mqtt.Client, userdata: dict[str, Any], msg: mqtt.MQTTMessage) -> None:
    """Delegate incoming messages to the telemetry handler."""
    handler = userdata.get("handler") if isinstance(userdata, dict) else None
    if not isinstance(handler, TelemetryMessageHandler):
        logger.error("MQTT handler missing from client userdata; dropping message topic=%s", msg.topic)
        return

    try:
        handler.handle(msg)
    except Exception:
        logger.exception("Unhandled error in MQTT message callback topic=%s", msg.topic)

