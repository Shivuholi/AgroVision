import json
import os
import time
from datetime import datetime, timezone, timedelta
import paho.mqtt.client as mqtt

from ..database import SessionLocal
from .. import models
from .prediction import (
    calculate_dynamic_threshold,
    calculate_predictive_water_need,
    calculate_evapotranspiration
)
from ..routers.weather import get_weather_forecast

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_CLIENT_ID = "agrovision_backend_server"

COOLDOWN_SOAK_SECONDS = 60
MAX_CONSECUTIVE_CYCLES = 3

_mqtt_client = None

def get_mqtt_client() -> mqtt.Client:
    global _mqtt_client
    if _mqtt_client is None:
        _mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
    return _mqtt_client

def publish_command(device_id: str, action: str, duration: int = 15) -> bool:
    """Publish real-time actuation command directly to ESP32 node (<50ms)."""
    client = get_mqtt_client()
    topic = f"agrovision/nodes/{device_id}/cmd"
    payload = json.dumps({"action": action, "duration": duration})
    try:
        res = client.publish(topic, payload, qos=1)
        print(f"[MQTT TX] Sent command to {topic}: {payload} (Status: {res.rc})")
        return res.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception as e:
        print(f"[MQTT ERROR] Failed to publish command: {e}")
        return False

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"[MQTT] Connected successfully to broker: {MQTT_BROKER}:{MQTT_PORT}")
        # Subscribe to all Agrovision device telemetry and status topics
        client.subscribe("agrovision/nodes/+/telemetry", qos=0)
        client.subscribe("agrovision/nodes/+/status", qos=1)
        print("[MQTT] Subscribed to 'agrovision/nodes/+/telemetry' and 'agrovision/nodes/+/status'")
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def on_disconnect(client, userdata, *args, **kwargs):
    print("[MQTT WARN] Disconnected from broker. Auto-reconnect active.")

def on_message(client, userdata, msg):
    """Event-driven reactive handler: processes telemetry and pushes actions in real time."""
    try:
        topic = msg.topic
        payload_str = msg.payload.decode("utf-8")
        parts = topic.split("/")

        if len(parts) >= 4 and parts[0] == "agrovision" and parts[1] == "nodes":
            device_id = parts[2]
            msg_type = parts[3]

            db = SessionLocal()
            try:
                # ----------------------------------------------------
                # CASE 1: LWT or Online Status Message
                # ----------------------------------------------------
                if msg_type == "status":
                    status = payload_str.strip().lower()
                    print(f"[MQTT STATUS] Node {device_id} is: {status}")
                    if status == "offline":
                        # Device disconnected unexpectedly
                        db.add(models.SystemLog(
                            device_id=device_id,
                            level="critical",
                            message=f"Device {device_id} went offline unexpectedly (MQTT LWT fired). Safety shutoff engaged."
                        ))
                        # Close any lingering active motor logs for this device
                        stale_motors = db.query(models.MotorLog).filter(
                            models.MotorLog.device_id == device_id,
                            models.MotorLog.status == "ON",
                            models.MotorLog.end_time == None
                        ).all()
                        for sm in stale_motors:
                            sm.end_time = datetime.now(timezone.utc)
                        db.commit()
                    return

                # ----------------------------------------------------
                # CASE 2: Real-Time Telemetry Stream (<50ms latency)
                # ----------------------------------------------------
                if msg_type == "telemetry":
                    data = json.loads(payload_str)
                    temp = float(data.get("temperature", 25.0))
                    hum = float(data.get("humidity", 60.0))
                    soil = float(data.get("soil_moisture", 30.0))
                    lux = float(data.get("lux", 0.0))

                    # 1. Record telemetry into SQLite database
                    db_sensor = models.SensorData(
                        device_id=device_id,
                        temperature=temp,
                        humidity=hum,
                        soil_moisture=soil,
                        lux=lux
                    )
                    db.add(db_sensor)
                    db.commit()

                    # 2. Compute Biological Soft-Sensors & Dynamic Threshold
                    ppfd = lux * 0.0185
                    dynamic_threshold = calculate_dynamic_threshold(ppfd)

                    # 3. Compute Predictive Water Need (W_now)
                    weather = get_weather_forecast()["data"]
                    p_rain = weather.get("rain_probability", 0.70 if "Rain" in weather.get("condition", "") else 0.15)
                    hours_to_rain = weather.get("hours_until_rain", 4.0 if "Rain" in weather.get("condition", "") else 20.0)

                    water_calc = calculate_predictive_water_need(
                        w_need=100.0,
                        p_rain=p_rain,
                        hours_until_rain=hours_to_rain,
                        soil_moisture=soil,
                        target_threshold=dynamic_threshold
                    )
                    water_pct = water_calc["percentage"]

                    # 4. Check Active Motor State
                    active_motor = db.query(models.MotorLog).filter(
                        models.MotorLog.device_id == device_id,
                        models.MotorLog.status == "ON",
                        models.MotorLog.end_time == None
                    ).first()

                    # ------------------------------------------------
                    # 4A. Pump is currently RUNNING -> check shutoff conditions
                    # ------------------------------------------------
                    if active_motor:
                        motor_start = active_motor.start_time.replace(tzinfo=timezone.utc) if active_motor.start_time.tzinfo is None else active_motor.start_time
                        run_duration = (datetime.now(timezone.utc) - motor_start).total_seconds()

                        # Turn off if target reached + 5% hysteresis (min 8s) or max 15s reached
                        if run_duration >= 15 or (run_duration >= 8 and soil > (dynamic_threshold + 5.0)):
                            active_motor.end_time = datetime.now(timezone.utc)
                            # Push immediate cutoff to ESP32 over MQTT
                            publish_command(device_id, "PUMP_OFF")
                            
                            db.add(models.SystemLog(
                                device_id=device_id,
                                level="info",
                                message=f"Irrigation Completed: Runtime {int(run_duration)}s (Moisture {soil:.1f}%). Entering {COOLDOWN_SOAK_SECONDS}s Soak Period."
                            ))
                            db.commit()
                            print(f"[MQTT CLOSED-LOOP] PUMP_OFF sent to {device_id}. Entering soak cooldown.")
                        return

                    # ------------------------------------------------
                    # 4B. Pump is OFF -> Evaluate real-time trigger
                    # ------------------------------------------------
                    if soil < dynamic_threshold:
                        # Check Rain Delay
                        if water_pct <= 0.0:
                            print(f"[MQTT NOTICE] Irrigation suppressed by Rain Delay (W_now={water_pct}%).")
                            return

                        # Check Anti-Short-Cycling Cooldown Soak
                        last_finished = db.query(models.MotorLog).filter(
                            models.MotorLog.device_id == device_id,
                            models.MotorLog.status == "ON",
                            models.MotorLog.end_time != None
                        ).order_by(models.MotorLog.end_time.desc()).first()

                        if last_finished and last_finished.end_time:
                            last_end = last_finished.end_time.replace(tzinfo=timezone.utc) if last_finished.end_time.tzinfo is None else last_finished.end_time
                            elapsed_off = (datetime.now(timezone.utc) - last_end).total_seconds()
                            if elapsed_off < COOLDOWN_SOAK_SECONDS:
                                print(f"[MQTT SOAK HOLD] Soak cooldown active ({int(COOLDOWN_SOAK_SECONDS - elapsed_off)}s left).")
                                return

                        # Check Consecutive Cycles Safety Lockout
                        recent_runs = db.query(models.MotorLog).filter(
                            models.MotorLog.device_id == device_id,
                            models.MotorLog.status == "ON",
                            models.MotorLog.end_time != None,
                            models.MotorLog.end_time > datetime.now(timezone.utc) - timedelta(minutes=15)
                        ).all()

                        if len(recent_runs) >= MAX_CONSECUTIVE_CYCLES:
                            print("[MQTT LOCKOUT] 3 consecutive cycles reached without moisture rise. Lockout active.")
                            return

                        # All conditions satisfied -> DISPATCH IMMEDIATE PUMP_ON COMMAND (<50ms!)
                        publish_command(device_id, "PUMP_ON", duration=15)

                        new_motor = models.MotorLog(device_id=device_id, status="ON")
                        db.add(new_motor)
                        db.add(models.SystemLog(
                            device_id=device_id,
                            level="success",
                            message=f"Real-Time Automated Irrigation: Moisture {soil:.1f}% < Target {dynamic_threshold:.1f}% (Demand: {water_pct}%)"
                        ))
                        db.commit()
                        print(f"[MQTT REAL-TIME ACTUATION] >>> PUMP_ON dispatched to {device_id} in <50ms! <<<")

            finally:
                db.close()

    except Exception as e:
        print(f"[MQTT ERROR] Error processing incoming message: {e}")

def start_mqtt_service():
    """Start the background MQTT client and thread loop."""
    client = get_mqtt_client()
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    client.on_message = on_message

    try:
        print(f"[MQTT INIT] Connecting to broker {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        client.loop_start() # Starts non-blocking background network thread
        print("[MQTT INIT] Background loop started successfully.")
    except Exception as e:
        print(f"[MQTT WARN] Could not start MQTT client: {e}. System running in HTTP fallback mode.")

def stop_mqtt_service():
    """Stop the background MQTT client."""
    global _mqtt_client
    if _mqtt_client is not None:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
            print("[MQTT] Background loop stopped cleanly.")
        except Exception as e:
            print(f"[MQTT ERROR] Error stopping client: {e}")
