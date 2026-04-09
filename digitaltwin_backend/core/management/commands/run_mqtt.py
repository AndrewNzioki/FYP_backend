import logging
from django.conf import settings
from django.core.management.base import BaseCommand
from core.mqtt.handlers import TelemetryMessageHandler, CommandAckHandler # 🚨 ADD CommandAckHandler here

# Bring in both of your handlers
from core.mqtt.handlers import TelemetryMessageHandler, CommandAckHandler
from core.mqtt.client import create_mqtt_client

logger = logging.getLogger(__name__)


# We must override the routing to handle both topics,
# since your original client factory only expected one handler.
def routed_on_message(client, userdata, msg):
    topic = msg.topic
    if topic == "plant/telemetry/state":
        userdata["telemetry_handler"].handle(client, userdata, msg)
    elif topic == "plant/command/ack":
        userdata["ack_handler"].handle(client, userdata, msg)
    else:
        logger.warning(f"Message received on unhandled topic: {topic}")


def routed_on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [DJANGO MQTT] Worker successfully connected to Mosquitto Broker!")
        client.subscribe("plant/telemetry/state", qos=1)
        # BRUTAL FIX: We must subscribe to the new ACK topic
        client.subscribe("plant/command/ack", qos=1)
        print("✅ [DJANGO MQTT] Subscribed to telemetry and ack topics.")
    else:
        print(f"❌ [DJANGO MQTT] Failed to connect, return code {rc}")


class Command(BaseCommand):
    help = "Runs the MQTT SCADA Listener (Telemetry & Command ACKs)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Initializing SCADA MQTT Worker (Listening Mode Only)..."))

        # 1. Setup Handlers
        telemetry_handler = TelemetryMessageHandler()
        ack_handler = CommandAckHandler()

        # 2. Use your existing factory, but we will override the routing
        client = create_mqtt_client(telemetry_handler, ack_handler)

        # Inject BOTH handlers into the userdata so the router can use them
        client.user_data_set({
            "telemetry_handler": telemetry_handler,
            "ack_handler": ack_handler
        })

        # Override the callbacks to use our new multi-topic routing
        client.on_message = routed_on_message
        client.on_connect = routed_on_connect

        try:
            self.stdout.write(
                f"Connecting to MQTT Broker at {settings.MQTT_BROKER_HOST}:{settings.MQTT_BROKER_PORT}...")

            client.connect(
                host=settings.MQTT_BROKER_HOST,
                port=settings.MQTT_BROKER_PORT,
                keepalive=settings.MQTT_KEEPALIVE,
            )

            # BRUTAL FIX: No more while True loop.
            # loop_forever() blocks the main thread and efficiently listens for incoming messages natively.
            client.loop_forever()

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nShutting down MQTT worker gracefully..."))
        except Exception as e:
            logger.error(f"MQTT Worker crashed critically: {e}")
            self.stdout.write(self.style.ERROR(f"Crash details: {e}"))
        finally:
            client.disconnect()
            self.stdout.write("MQTT disconnected. Worker terminated.")