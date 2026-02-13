# fake_edge.py
import json
import time
import random
import paho.mqtt.client as mqtt

BROKER = "localhost"
PORT = 1883
TANK_TOPIC = "tank/levels"
COMMAND_TOPIC = "tank/commands"

# --- MQTT Callbacks ---
def on_connect(client, userdata, flags, rc):
    print(f"Connected with result code {rc}")
    client.subscribe(COMMAND_TOPIC)

def on_message(client, userdata, msg):
    print(f"Received command: {msg.topic} -> {msg.payload.decode()}")

# --- Client Setup ---
client = mqtt.Client(client_id="FakeEdge", protocol=mqtt.MQTTv311)
client.on_connect = on_connect
client.on_message = on_message
client.connect(BROKER, PORT, 60)
client.loop_start()

# --- Main Loop ---
try:
    while True:
        # Simulate tank levels
        tank_levels = {
            "tank1": round(random.uniform(10, 100), 2),
            "tank2": round(random.uniform(10, 100), 2),
            "source": round(random.uniform(5, 100), 2),
        }
        payload = json.dumps(tank_levels)
        client.publish(TANK_TOPIC, payload)
        print(f"Published tank levels: {payload}")
        time.sleep(2)  # publish every 2 seconds

except KeyboardInterrupt:
    client.loop_stop()
    print("Fake edge stopped")
