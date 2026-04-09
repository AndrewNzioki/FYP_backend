import paho.mqtt.client as mqtt
import json
import time
from decouple import config

# --- CONFIGURATION ---
MQTT_BROKER = config('MQTT_BROKER_HOST', default='localhost')
MQTT_PORT = config('MQTT_BROKER_PORT', default=1883, cast=int)
TOPIC_TELEMETRY = config('MQTT_TELEMETRY_STATE_TOPIC', default='plant/telemetry/state')
TOPIC_COMMAND_SUB = "plant/command/#"
TOPIC_COMMAND_ACK = "plant/command/ack"  # New Dedicated ACK topic


class VirtualMaster:
    def __init__(self):
        self.mode = 0
        self.source_lvl = 100.0
        self.source_fault = False
        self.pump_actual = False
        self.municipal_supply_active = False

        self.start_time = time.time()
        self.transition_start_time = 0.0
        self.active_valves = []

        self.tanks = {
            1: {"level": 60.0, "status": 0, "valve": False},
            2: {"level": 85.0, "status": 0, "valve": False}
        }

    def simulate_physics(self):
        # 1. Simulate Rooftop Usage (Draining)
        for t_id, t_data in self.tanks.items():
            if not t_data["valve"]:
                t_data["level"] -= 0.2
                if t_data["level"] < 0: t_data["level"] = 0.0

        # 2. MUNICIPAL REFILL LOGIC
        if self.source_lvl <= 40.0:
            if not self.municipal_supply_active:
                print("\n🚰 [EDGE PLC] City water detected. Refilling Source Tank...")
            self.municipal_supply_active = True

        if self.municipal_supply_active:
            self.source_lvl += 0.8
            if self.source_lvl >= 100.0:
                self.source_lvl = 100.0
                self.municipal_supply_active = False

        # 3. EDGE SAFETY VETO: LOW SUPPLY
        if self.mode in [1, 2] and self.source_lvl <= 20.0:
            print("\n⚠️ [EDGE PLC] SOURCE DEPLETED! Vetoing pump. Entering LOW_SUPPLY mode.")
            self.mode = 3
            self.pump_actual = False
            for v in self.active_valves: self.tanks[v]["valve"] = False

        # 4. EDGE RECOVERY: LOW SUPPLY
        if self.mode == 3 and self.source_lvl >= 40.0:
            print("\n✅ [EDGE PLC] Source Recovered above 40%. Returning to IDLE.")
            self.mode = 0
            self.active_valves = []

        # 5. MODE 1: HYDRAULIC TRANSITION
        if self.mode == 1 and len(self.active_valves) > 0:
            for v in self.active_valves:
                self.tanks[v]["valve"] = True

            if time.time() - self.transition_start_time >= 2.0:
                print(f"\n[EDGE PLC] Valves {self.active_valves} confirmed OPEN. Starting Pump.")
                self.mode = 2
                self.pump_actual = True

        # 6. MODE 2: PUMPING TO ROOF
        if self.mode == 2 and len(self.active_valves) > 0:
            drain_rate = 0.5 * len(self.active_valves)
            self.source_lvl -= drain_rate

            valves_to_close = []
            for v in self.active_valves:
                self.tanks[v]["level"] += 2.0

                if self.tanks[v]["level"] >= 95.0:
                    print(f"\n[EDGE PLC] Tank {v} Full (95%). Closing its valve.")
                    self.tanks[v]["valve"] = False
                    valves_to_close.append(v)

            for v in valves_to_close:
                self.active_valves.remove(v)

            if len(self.active_valves) == 0:
                print("\n[EDGE PLC] All requested tanks full. Shutting down pump. Returning to IDLE.")
                self.pump_actual = False
                self.mode = 0

        # 7. MODE 0: AUTONOMOUS PRIORITY (BRUTAL FIX: Now fills ALL needy tanks simultaneously)
        if self.mode == 0:
            needy_tanks = [t_id for t_id, t_data in self.tanks.items() if
                           t_data["level"] <= 30.0 and t_data["status"] == 0]
            if needy_tanks:
                print(f"\n[EDGE PLC] Autonomous Fill: Tanks {needy_tanks} hit <= 30%. Entering TRANSITION.")
                self.mode = 1
                self.active_valves = needy_tanks
                self.transition_start_time = time.time()

    def handle_cloud_intent(self, command_id, command_type, payload):
        print(f"\n[EDGE PLC] Command Received: {command_type} | ID: {command_id} | Payload: {payload}")

        status = "ACKNOWLEDGED"
        msg = f"Executing {command_type}"

        if command_type == "SUPPLY_TANKS":
            targets = payload.get("target_tanks", [])
            if self.mode == 4:
                status, msg = "REJECTED", "HARDWARE VETO: System is in FAULT state."
                print(f"[EDGE PLC] {msg}")
            elif self.source_fault:
                status, msg = "REJECTED", "HARDWARE VETO: Source tank sensor is faulted."
                print(f"[EDGE PLC] {msg}")
            else:
                # 🚨 Edge-level validation against faults and redundant commands
                valid_targets = [t for t in targets if
                                 t in self.tanks and self.tanks[t]["status"] == 0 and t not in self.active_valves]

                if not valid_targets:
                    status, msg = "REJECTED", "IGNORING: No valid, healthy, non-filling targets provided."
                    print(f"[EDGE PLC] {msg}")
                else:
                    msg = f"EXECUTING: Forcing valves open for {valid_targets}"
                    print(f"[EDGE PLC] {msg}")
                    self.active_valves = list(set(self.active_valves + valid_targets))
                    self.mode = 1
                    self.transition_start_time = time.time()

        elif command_type == "STOP_SUPPLY_TANKS":
            targets = payload.get("target_tanks", [])
            for t in targets:
                if t in self.active_valves:
                    print(f"[EDGE PLC] EXECUTING: Closing valve for Tank {t}")
                    self.tanks[t]["valve"] = False
                    self.active_valves.remove(t)
            if len(self.active_valves) == 0:
                self.mode = 0
                self.pump_actual = False

        elif command_type == "EMERGENCY_STOP":
            print("\n🚨 [EDGE PLC] EMERGENCY STOP EXECUTED BY ADMIN 🚨")
            self.mode = 4
            self.pump_actual = False
            self.active_valves = []
            for t in self.tanks.values(): t["valve"] = False

        elif command_type == "CLEAR_FAULT":
            if self.mode != 4:
                status, msg = "REJECTED", "IGNORING: System is not in FAULT mode."
                print(f"[EDGE PLC] {msg}")
            else:
                hw_faults = [t_id for t_id, t_data in self.tanks.items() if t_data["status"] != 0]
                if self.source_fault or hw_faults:
                    status, msg = "REJECTED", f"VETO: Cannot clear fault! Hardware errors exist on Tanks: {hw_faults} or Source."
                    print(f"\n❌ [EDGE PLC] {msg}")
                else:
                    print("\n✅ [EDGE PLC] EXECUTING: Software fault cleared (Admin E-Stop Reset). Returning to IDLE.")
                    self.mode = 0

        return status, msg

    def generate_payload(self):
        return {
            "mode": self.mode,
            "source_level_percent": round(self.source_lvl, 1),
            "source_fault": self.source_fault,
            "pump_actual": self.pump_actual,
            "tanks": [{"id": t_id, "level_percent": round(t_data["level"], 1), "status": t_data["status"],
                       "valve_actual": t_data["valve"]} for t_id, t_data in self.tanks.items()]
        }


edge_plc = VirtualMaster()


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("✅ [WIFI] Edge PLC Connected to Broker")
        client.subscribe(TOPIC_COMMAND_SUB, qos=2)


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        command_id = data.get("command_id")
        command_type = data.get("command_type")
        payload = data.get("target_payload", data.get("payload", {}))  # Catch both new and old keys

        if command_id and command_type:
            # 1. Edge processes the logic
            status, ack_msg = edge_plc.handle_cloud_intent(command_id, command_type, payload)

            # 2. Edge INSTANTLY fires back an ACK
            ack_payload = {
                "command_id": command_id,
                "status": status,
                "message": ack_msg
            }
            client.publish(TOPIC_COMMAND_ACK, json.dumps(ack_payload), qos=1)
            print(f"📤 [EDGE PLC] Sent Handshake ACK: {status} to Cloud.")

    except Exception as e:
        print(f"[EDGE PLC] JSON Parse Error: {e}")


print("🚀 Booting Multi-Valve Edge PLC with Cloud Handshake Protocol...")
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    print(f"CRITICAL: Broker offline ({e})")
    exit(1)

try:
    while True:
        edge_plc.simulate_physics()
        telemetry = edge_plc.generate_payload()

        print(
            f"📡 [1Hz] Mode: {telemetry['mode']} | Src: {telemetry['source_level_percent']}% | T1: {telemetry['tanks'][0]['level_percent']}% | T2: {telemetry['tanks'][1]['level_percent']}% | Pump: {'ON' if telemetry['pump_actual'] else 'OFF'} | Act: {edge_plc.active_valves}")

        client.publish(TOPIC_TELEMETRY, json.dumps(telemetry), qos=1)
        time.sleep(1.0)
except KeyboardInterrupt:
    client.loop_stop()
    client.disconnect()