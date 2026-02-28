import paho.mqtt.client as mqtt
import time
import json
import random

# Use the exact broker details from your Django .env
BROKER_HOST = "127.0.0.1"
BROKER_PORT = 1883
TELEMETRY_TOPIC = "plant/telemetry/state"
COMMAND_TOPIC = "plant/command/set_mode"

# Initial Physical State of the "Hardware"
state = {
    "mode": "IDLE",
    "tank1_level": 40.0,
    "tank2_level": 30.0,
    "source_level": 85.0,
    "pump_command": "OFF",
    "pump_actual": "OFF",
    "valve1_command": "CLOSED",
    "valve1_actual": "CLOSED",
    "valve2_command": "CLOSED",
    "valve2_actual": "CLOSED",
    "tank1_sensor_status": "OK",
    "tank2_sensor_status": "OK",
    "source_sensor_status": "OK",
    "cloud_connection_status": "CONNECTED",
    "emergency_stop": False
}

# Local Edge Configuration (Defaults)
edge_config = {
    "LOW_THRESHOLD": 20.0
}


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[EDGE] Connected to broker successfully.")
        client.subscribe(COMMAND_TOPIC, qos=2)
        print(f"[EDGE] Subscribed to {COMMAND_TOPIC}")
    else:
        print(f"[EDGE] Failed to connect, return code {rc}")


def on_message(client, userdata, msg):
    print(f"\n[EDGE] >>> RECEIVED COMMAND: {msg.payload.decode()}")
    try:
        payload = json.loads(msg.payload.decode())
        command_type = payload.get("command_type")
        cmd_payload = payload.get("payload", {})

        if command_type == "REQUEST_MODE_CHANGE":
            target = cmd_payload.get("target_mode")
            if target:
                state["mode"] = target
                print(f"[EDGE] Mode switched to {target}. Actuators engaging next tick...")

        # --- ADD THIS BLOCK FOR DYNAMIC CONFIGURATION ---
        elif command_type == "MODIFY_CONSTANTS":
            for key, value in cmd_payload.items():
                edge_config[key] = float(value)
            print(f"[EDGE-CONFIG] Applied new safety thresholds: {edge_config}")
        # ------------------------------------------------

    except json.JSONDecodeError:
        print("[EDGE] Error: Received malformed JSON command.")

# Setup MQTT Client
client = mqtt.Client(client_id="esp32_simulator_001")
client.on_connect = on_connect
client.on_message = on_message

# --- ADD THIS: THE LAST WILL AND TESTAMENT ---
death_note = json.dumps({"cloud_connection_status": "LOST"})
client.will_set(TELEMETRY_TOPIC, payload=death_note, qos=1, retain=False)
# ---------------------------------------------

print("Starting Fake Edge Node...")
client.connect(BROKER_HOST, BROKER_PORT, 5)
client.loop_start()

try:
    while True:
        # --- LOCAL AUTONOMOUS SAFETY INTERLOCK ---
        # The Edge protects itself. If water is critically low, it forces LOW_SUPPLY mode
        # and kills the pump instantly, ignoring the Cloud's intent.
        if state["source_level"] <= edge_config["LOW_THRESHOLD"] and state["mode"] == "FILLING":
            print(f"[EDGE-CRITICAL] SOURCE < {edge_config['LOW_THRESHOLD']}%. LOCAL OVERRIDE ENGAGED. CUTTING PUMP.")
            state["mode"] = "LOW_SUPPLY"
            state["pump_command"] = "OFF"
            state["pump_actual"] = "OFF"
            state["valve1_command"] = "CLOSED"
            state["valve1_actual"] = "CLOSED"
        # -----------------------------------------

        # 1. Simulate Physical Water Dynamics
        if state["mode"] == "FILLING":
            state["pump_command"] = "ON"
            state["pump_actual"] = "ON"
            state["valve1_command"] = "OPEN"
            state["valve1_actual"] = "OPEN"

            # Source drains
            state["source_level"] = max(0.0, state["source_level"] - 8.0)
            state["tank1_level"] = min(100.0, state["tank1_level"] + 2.0)

        elif state["mode"] == "IDLE" or state["mode"] == "LOW_SUPPLY":
            state["pump_command"] = "OFF"
            state["pump_actual"] = "OFF"
            state["valve1_command"] = "CLOSED"
            state["valve1_actual"] = "CLOSED"
            # Simulate very slow source refill
            state["source_level"] = min(100.0, state["source_level"] + 1.0)

        # 2. Publish Telemetry to the Cloud
        print(
            f"[EDGE] Telemetry -> Mode: {state['mode']} | Pump: {state['pump_actual']} | Source: {state['source_level']:.1f}% | Tank1: {state['tank1_level']:.1f}%")

        client.publish(TELEMETRY_TOPIC, json.dumps(state), qos=1)

        time.sleep(3)  # Sped up from 5 seconds for testing


except KeyboardInterrupt:
    print("\n[EDGE] Shutting down simulation...")
    client.loop_stop()
   #client.disconnect()