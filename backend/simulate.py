import time
import random
import json
import os
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
DEVICE_ID = "ESP32_01"

TOPIC_TELEMETRY = f"agrovision/nodes/{DEVICE_ID}/telemetry"
TOPIC_COMMAND   = f"agrovision/nodes/{DEVICE_ID}/cmd"
TOPIC_STATUS    = f"agrovision/nodes/{DEVICE_ID}/status"

is_pumping = False
pump_start_time = 0
configured_duration = 15

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[SIMULATOR] Connected to MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
        client.publish(TOPIC_STATUS, "online", retain=True)
        client.subscribe(TOPIC_COMMAND, qos=1)
        print(f"[SIMULATOR] Subscribed to command topic: {TOPIC_COMMAND}")
    else:
        print(f"[SIMULATOR] Connection failed with rc {rc}")

def on_message(client, userdata, msg):
    global is_pumping, pump_start_time, configured_duration
    try:
        payload = json.loads(msg.payload.decode("utf-8"))
        action = payload.get("action")
        duration = payload.get("duration", 15)

        if action == "PUMP_ON":
            is_pumping = True
            pump_start_time = time.time()
            configured_duration = duration
            print(f"\n[ACTUATOR RX] >>> PUMP TURNED ON (Duration: {duration}s) via MQTT in <50ms! <<<")
        elif action == "PUMP_OFF":
            is_pumping = False
            print("\n[ACTUATOR RX] >>> PUMP TURNED OFF via MQTT! <<<")
    except Exception as e:
        print(f"[SIMULATOR ERROR] Error processing message: {e}")

def simulate_esp32_mqtt():
    global is_pumping, pump_start_time, configured_duration
    print("==================================================")
    print(f"  AgroVision ESP32 Real-Time MQTT Simulator       ")
    print(f"  Target: {DEVICE_ID} on {MQTT_BROKER}            ")
    print("==================================================")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"simulator_{DEVICE_ID}")
    client.will_set(TOPIC_STATUS, "offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start()
    except Exception as e:
        print(f"[ERROR] Could not connect to MQTT broker: {e}")
        return

    # Initial state
    temp = 28.0
    hum = 55.0
    soil = 42.0
    lux = 3500.0

    last_pub = 0
    try:
        while True:
            now = time.time()

            # Autonomous Hardware Failsafe cutoff (Edge Watchdog Simulation)
            if is_pumping:
                elapsed = now - pump_start_time
                soil += random.uniform(2.5, 4.0) # Soil absorbs water
                if elapsed >= configured_duration or elapsed >= 20.0:
                    is_pumping = False
                    print(f"\n[LOCAL HARDWARE CUTOFF] Pump stopped after {int(elapsed)}s run time.")
            else:
                # Soil naturally drying under solar radiation
                soil_drop = 0.4 if temp > 30 else 0.2
                soil -= random.uniform(soil_drop - 0.05, soil_drop + 0.1)

            # Environmental micro-climate drift
            temp += random.uniform(-0.3, 0.3)
            hum += random.uniform(-0.5, 0.5)
            lux += random.uniform(-100, 100)

            # Bounds
            temp = max(18.0, min(temp, 42.0))
            hum = max(30.0, min(hum, 95.0))
            soil = max(10.0, min(soil, 95.0))
            lux = max(100.0, min(lux, 65000.0))

            # Push telemetry every 5 seconds
            if now - last_pub >= 5.0:
                last_pub = now
                payload = {
                    "device_id": DEVICE_ID,
                    "temperature": round(temp, 1),
                    "humidity": round(hum, 1),
                    "soil_moisture": round(soil, 1),
                    "lux": round(lux, 1),
                    "pump_active": is_pumping
                }
                client.publish(TOPIC_TELEMETRY, json.dumps(payload))
                pump_str = "ON [PUMPING]" if is_pumping else "OFF [IDLE]"
                print(f"[Telemetry TX] Soil: {soil:.1f}% | Temp: {temp:.1f}C | Lux: {lux:.0f} lx | Pump: {pump_str}")

            time.sleep(0.5) # Sub-second event loop

    except KeyboardInterrupt:
        print("\nStopping simulator...")
        client.publish(TOPIC_STATUS, "offline", retain=True)
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    simulate_esp32_mqtt()
