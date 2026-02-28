import time
import logging
import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand

# Import your handlers from your existing codebase
from core.mqtt.handlers import TelemetryMessageHandler
from core.mqtt.client import create_mqtt_client
from core.mqtt.publisher import CommandPublisher

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Runs the MQTT worker for the Digital Twin'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Initializing MQTT Worker...'))

        # 1. Initialize Handlers and Client
        handler = TelemetryMessageHandler()
        client = create_mqtt_client(handler)
        publisher = CommandPublisher(client)

        try:
            # 2. Connect to Broker using settings
            self.stdout.write(
                f"Connecting to MQTT Broker at {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")
            client.connect(
                host=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
                keepalive=settings.MQTT_KEEPALIVE
            )

            # 3. Start the background network thread for incoming messages
            client.loop_start()
            self.stdout.write(self.style.SUCCESS('MQTT Worker running. Listening for telemetry and pushing commands.'))

            # 4. The Infinite Command Publishing Loop
            poll_interval = getattr(settings, 'MQTT_COMMAND_POLL_INTERVAL_SECONDS', 1.0)

            while True:
                try:
                    # Push any commands sitting in the DB as "APPROVED"
                    published_count = publisher.publish_approved_commands()
                    if published_count > 0:
                        self.stdout.write(
                            self.style.SUCCESS(f"Successfully published {published_count} queued commands."))
                except Exception as loop_err:
                    logger.error(f"Error during command publish loop: {loop_err}")

                # Sleep to avoid CPU thrashing
                time.sleep(poll_interval)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\nShutting down MQTT Worker gracefully...'))
        except Exception as e:
            logger.error(f"MQTT Worker crashed critically: {e}")
            self.stdout.write(self.style.ERROR(f"Crash details: {e}"))
        finally:
            # Always clean up
            client.loop_stop()
            client.disconnect()
            self.stdout.write('MQTT disconnected. Worker terminated.')