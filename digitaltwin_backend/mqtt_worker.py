"""Standalone MQTT worker process for Django backend.

Run this worker separately from the web server:
    python mqtt_worker.py
"""

from __future__ import annotations

import logging
import os
import signal
import threading

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "digitaltwin_backend.settings")
django.setup()

from django.conf import settings

from core.mqtt.client import create_mqtt_client
from core.mqtt.handlers import TelemetryMessageHandler
from core.mqtt.publisher import CommandPublisher

logger = logging.getLogger("mqtt_worker")


def _configure_logging() -> None:
    """Ensure worker logging has a fallback format if Django logging is not configured."""
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
            format="%(levelname)s %(asctime)s %(name)s %(message)s",
        )


def main() -> None:
    """Run MQTT background worker with reconnect and command polling loop."""
    _configure_logging()

    stop_event = threading.Event()
    handler = TelemetryMessageHandler()
    client = create_mqtt_client(handler=handler)
    publisher = CommandPublisher(client=client)

    def _request_shutdown(*_: object) -> None:
        logger.info("Shutdown signal received; stopping worker loop.")
        stop_event.set()

    signal.signal(signal.SIGINT, _request_shutdown)
    signal.signal(signal.SIGTERM, _request_shutdown)

    logger.info(
        "Starting MQTT worker host=%s port=%s tls=%s",
        settings.MQTT_BROKER_HOST,
        settings.MQTT_BROKER_PORT,
        settings.MQTT_TLS_ENABLED,
    )

    client.connect_async(
        host=settings.MQTT_BROKER_HOST,
        port=settings.MQTT_BROKER_PORT,
        keepalive=settings.MQTT_KEEPALIVE,
    )
    client.loop_start()

    try:
        while not stop_event.is_set():
            try:
                published_count = publisher.publish_approved_commands()
                if published_count:
                    logger.info("Published %s command(s) in this poll cycle.", published_count)
            except Exception:
                logger.exception("Unhandled exception in command polling loop")

            stop_event.wait(settings.MQTT_COMMAND_POLL_INTERVAL_SECONDS)
    finally:
        logger.info("Stopping MQTT network loop and disconnecting client.")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()

