import time
import logging
from django.conf import settings
from django.core.management.base import BaseCommand

from core.mqtt.handlers import TelemetryMessageHandler
from core.mqtt.client import create_mqtt_client
from core.mqtt.publisher import CommandPublisher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Runs the MQTT telemetry worker and Command Publisher"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Initializing SCADA MQTT Worker (Ingestion & Dispatch)..."))

        # 1. Setup Listener
        handler = TelemetryMessageHandler()
        client = create_mqtt_client(handler)

        # 2. Setup Publisher
        publisher = CommandPublisher(client)

        try:
            self.stdout.write(
                f"Connecting to MQTT Broker at {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")
            client.connect(
                host=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
                keepalive=settings.MQTT_KEEPALIVE,
            )

            # loop_start() runs the receiving network traffic in a background thread
            client.loop_start()
            self.stdout.write(self.style.SUCCESS("MQTT worker connected. Listening for edge telemetry..."))

            # 3. The Main Polling Loop
            while True:
                try:
                    # Check the database for APPROVED commands and publish them
                    published_count = publisher.publish_approved_commands()
                    if published_count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f"Successfully dispatched {published_count} commands to the Edge."))
                except Exception as db_err:
                    logger.error(f"Database polling error in publisher loop: {db_err}")

                # Sleep for 1 second before checking again to prevent CPU thrashing
                time.sleep(1.0)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nShutting down MQTT worker gracefully..."))
        except Exception as e:
            logger.error(f"MQTT Worker crashed critically: {e}")
            self.stdout.write(self.style.ERROR(f"Crash details: {e}"))
        finally:
            client.loop_stop()
            client.disconnect()
            self.stdout.write("MQTT disconnected. Worker terminated.")