import logging
import paho.mqtt.client as mqtt
from django.conf import settings
from django.core.management.base import BaseCommand
from core.mqtt.handlers import TelemetryMessageHandler, CommandAckHandler

logger = logging.getLogger(__name__)


# ==========================================
# MULTI-TOPIC ROUTER
# ==========================================
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
        print("✅ [DJANGO MQTT] Worker successfully connected to Broker!")
        client.subscribe("plant/telemetry/state", qos=1)
        client.subscribe("plant/command/ack", qos=1)
        print("✅ [DJANGO MQTT] Subscribed to telemetry and ack topics.")
    else:
        print(f"❌ [DJANGO MQTT] Failed to connect, return code {rc}")


# ==========================================
# DJANGO MANAGEMENT COMMAND
# ==========================================
class Command(BaseCommand):
    help = "Runs the MQTT SCADA Listener (Telemetry & Command ACKs)"

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Initializing SCADA MQTT Worker (Listening Mode Only)..."))

        # 1. Setup Handlers
        telemetry_handler = TelemetryMessageHandler()
        ack_handler = CommandAckHandler()

        # 2. Instantiate Raw Client (Bypasses any hardcoded SSL in factories)
        client = mqtt.Client()

        # 3. Inject Handlers into Userdata for the router
        client.user_data_set({
            "telemetry_handler": telemetry_handler,
            "ack_handler": ack_handler
        })

        # 4. Attach Callbacks
        client.on_message = routed_on_message
        client.on_connect = routed_on_connect

        # 5. Fetch Settings (Defaulting to localhost if missing)
        broker_host = getattr(settings, 'MQTT_BROKER_HOST', 'localhost')
        broker_port = getattr(settings, 'MQTT_BROKER_PORT', 1883)

        # 6. The SSL / Localhost Fix
        if broker_port == 8883:
            self.stdout.write("🔒 Configuring TLS for secure cloud connection...")
            client.tls_set()
            # Apply credentials if they exist for cloud
            mqtt_user = getattr(settings, 'MQTT_USER', None)
            mqtt_pass = getattr(settings, 'MQTT_PASS', None)
            if mqtt_user and mqtt_pass:
                client.username_pw_set(mqtt_user, mqtt_pass)
        else:
            self.stdout.write("🔓 Using plain-text local connection (SSL disabled)...")

        # 7. Connect and Run Blocking Loop
        try:
            self.stdout.write(f"Connecting to MQTT Broker at {broker_host}:{broker_port}...")

            client.connect(
                host=broker_host,
                port=broker_port,
                keepalive=getattr(settings, 'MQTT_KEEPALIVE', 60),
            )

            # loop_forever() efficiently blocks the thread and manages reconnects natively
            client.loop_forever()

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nShutting down MQTT worker gracefully..."))
        except Exception as e:
            logger.error(f"MQTT Worker crashed critically: {e}")
            self.stdout.write(self.style.ERROR(f"Crash details: {e}"))
        finally:
            client.disconnect()
            self.stdout.write("MQTT disconnected. Worker terminated.")