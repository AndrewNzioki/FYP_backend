import paho.mqtt.client as mqtt
import ssl
import certifi
import time
import random

# 🚨 Type these in manually. NO .env variables.
BROKER = "a2ad66fb959e4a8288e475f1b178c532.s1.eu.hivemq.cloud"
PORT = 8883
USERNAME = "scada_master"  # <-- Verify this in your HiveMQ Access Management
PASSWORD = "UMfmxwtQ!a6LuWC" # <-- Verify this matches exactly

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ SUCCESS! Connected to HiveMQ!")
    else:
        print(f"❌ FAILED! Broker rejected connection with code: {rc}")

def on_disconnect(client, userdata, rc):
    print(f"⚠️ Disconnected with code: {rc}")

# 🚨 We generate a random Client ID to bypass any zombie processes
client_id = f"test_worker_{random.randint(1000, 9999)}"
client = mqtt.Client(client_id=client_id, clean_session=True)

client.on_connect = on_connect
client.on_disconnect = on_disconnect
client.enable_logger()

# Set credentials and strict TLS
client.username_pw_set(USERNAME, PASSWORD)
client.tls_set(ca_certs=certifi.where(), tls_version=ssl.PROTOCOL_TLSv1_2)

print(f"Attempting to connect to {BROKER} as {client_id}...")
try:
    client.connect(BROKER, PORT, 60)
    client.loop_start()
    time.sleep(5) # Wait 5 seconds to see if it holds the connection
    client.loop_stop()
    print("Test complete.")
except Exception as e:
    print(f"Fatal Crash: {e}")