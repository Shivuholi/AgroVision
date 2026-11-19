import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from .. import models
from ..database import SessionLocal
from .prediction import (
    calculate_evapotranspiration,
    predict_moisture_drop,
    calculate_dynamic_threshold,
    calculate_predictive_water_need
)
from ..routers.weather import get_weather_forecast

# The threshold is now dynamic based on Light Stress (PPFD)

COOLDOWN_SOAK_SECONDS = 60  # Minimum 60s soak time between irrigation cycles
MAX_CONSECUTIVE_CYCLES = 3  # Protect against dry well, sensor dislocation, or overflow

async def run_control_loop():
    # Startup cleanup: close any stale open motor logs from prior crash/restart
    try:
        startup_db = SessionLocal()
        stale_motors = startup_db.query(models.MotorLog).filter(
            models.MotorLog.status == "ON",
            models.MotorLog.end_time == None
        ).all()
        for sm in stale_motors:
            sm.end_time = datetime.now(timezone.utc)
        if stale_motors:
            startup_db.commit()
            print(f"[STARTUP] Cleaned up {len(stale_motors)} stale active motor logs.")
        startup_db.close()
    except Exception as e:
        print(f"[STARTUP WARNING] Could not clean stale logs: {e}")

    while True:
        try:
            db = SessionLocal()
            
            # 1. Get latest sensor data (assume 1 device for now: "ESP32_01")
            latest_data = db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).first()
            
            if latest_data:
                # 2. Get manual NPK entry
                latest_npk = db.query(models.NutrientEntry).order_by(models.NutrientEntry.timestamp.desc()).first()
                if latest_npk:
                    pass
                
                # 3. Get weather forecast
                weather = get_weather_forecast()["data"]
                
                # 4. Predict ET and future moisture (Crop Coefficient Kc = 1.2 for demo)
                et_data = calculate_evapotranspiration(
                    temp_c=weather["temperature_c"],
                    humidity=weather["humidity_percent"],
                    wind_speed=weather["wind_speed_ms"],
                    solar_rad=weather["solar_radiation_wm2"],
                    kc=1.2
                )
                et_rate = et_data["et_c"]
                
                predicted_moisture = predict_moisture_drop(
                    current_moisture=latest_data.soil_moisture,
                    et_rate=et_rate,
                    hours_ahead=12 # predict 12 hours ahead
                )
                # 4.5. Calculate Dynamic Threshold based on Light Stress
                ppfd = latest_data.ppfd
                dynamic_threshold = calculate_dynamic_threshold(ppfd)
                
                # 4.6. Calculate Predictive Water Need (W_now formula)
                p_rain = weather.get("rain_probability", 0.70 if "Rain" in weather.get("condition", "") else 0.15)
                hours_to_rain = weather.get("hours_until_rain", 4.0 if "Rain" in weather.get("condition", "") else 20.0)
                
                water_calc = calculate_predictive_water_need(
                    w_need=100.0,
                    p_rain=p_rain,
                    hours_until_rain=hours_to_rain,
                    soil_moisture=latest_data.soil_moisture,
                    target_threshold=dynamic_threshold
                )
                water_pct = water_calc["percentage"]
                
                # 5. Check active motor state (State Hold ON & Safety Timeout)
                active_motors = db.query(models.MotorLog).filter(
                    models.MotorLog.device_id == latest_data.device_id,
                    models.MotorLog.status == "ON",
                    models.MotorLog.end_time == None
                ).all()

                if active_motors:
                    for motor in active_motors:
                        motor_start = motor.start_time.replace(tzinfo=timezone.utc) if motor.start_time.tzinfo is None else motor.start_time
                        run_duration = (datetime.now(timezone.utc) - motor_start).total_seconds()

                        # Turn off if soil reaches threshold + 5% hysteresis (min 8s run) OR after max 15 seconds
                        if run_duration >= 15 or (run_duration >= 8 and latest_data.soil_moisture > (dynamic_threshold + 5.0)):
                            motor.end_time = datetime.now(timezone.utc)

                            new_cmd = models.ControlCommand(
                                device_id=latest_data.device_id,
                                command_type="PUMP_OFF",
                                status="PENDING"
                            )
                            db.add(new_cmd)
                            db.add(models.SystemLog(
                                device_id=latest_data.device_id,
                                level="info",
                                message=f"Irrigation Completed: Runtime {int(run_duration)}s (Moisture {latest_data.soil_moisture:.1f}%). Entering {COOLDOWN_SOAK_SECONDS}s Soak Period."
                            ))
                            db.commit()
                            print(f"Scheduled PUMP_OFF for {latest_data.device_id} (Runtime: {int(run_duration)}s). Entering Soak Period.")
                    
                    db.close()
                    await asyncio.sleep(5)
                    continue

                # 6. Motor is OFF: evaluate whether to trigger a new cycle
                if latest_data.soil_moisture < dynamic_threshold:
                    # 6.1. RAIN PREDICTION CHECK
                    if water_pct <= 0.0:
                        last_rain_log = db.query(models.SystemLog).filter(
                            models.SystemLog.message.contains("Rain Delay"),
                            models.SystemLog.timestamp > datetime.now(timezone.utc) - timedelta(hours=1)
                        ).first()

                        if not last_rain_log:
                            db.add(models.SystemLog(
                                device_id=latest_data.device_id,
                                level="warning",
                                message=f"Predictive Rain Delay: Water need {water_pct}% ({water_calc['status_label']}). Skipping irrigation."
                            ))
                            db.commit()
                        print(f"Irrigation inhibited by predictive water need (W_now={water_pct}%). Condition: {weather.get('condition')}")
                        db.close()
                        await asyncio.sleep(5)
                        continue

                    # 6.2. COOLDOWN SOAK HOLD (Anti-Short-Cycling / Infiltration Lock)
                    last_finished_motor = db.query(models.MotorLog).filter(
                        models.MotorLog.device_id == latest_data.device_id,
                        models.MotorLog.status == "ON",
                        models.MotorLog.end_time != None
                    ).order_by(models.MotorLog.end_time.desc()).first()

                    if last_finished_motor and last_finished_motor.end_time:
                        last_end_utc = last_finished_motor.end_time.replace(tzinfo=timezone.utc) if last_finished_motor.end_time.tzinfo is None else last_finished_motor.end_time
                        time_since_last_off = (datetime.now(timezone.utc) - last_end_utc).total_seconds()

                        if time_since_last_off < COOLDOWN_SOAK_SECONDS:
                            remaining_soak = int(COOLDOWN_SOAK_SECONDS - time_since_last_off)
                            print(f"[STATE HOLD: OFF] Soak cooldown active ({remaining_soak}s remaining). Holding state OFF.")
                            db.close()
                            await asyncio.sleep(5)
                            continue

                    # 6.3. DRY RUN / SENSOR FAULT PROTECTION
                    recent_runs = db.query(models.MotorLog).filter(
                        models.MotorLog.device_id == latest_data.device_id,
                        models.MotorLog.status == "ON",
                        models.MotorLog.end_time != None,
                        models.MotorLog.end_time > datetime.now(timezone.utc) - timedelta(minutes=15)
                    ).all()

                    if len(recent_runs) >= MAX_CONSECUTIVE_CYCLES:
                        last_alarm = db.query(models.SystemLog).filter(
                            models.SystemLog.message.contains("Safety Lockout"),
                            models.SystemLog.timestamp > datetime.now(timezone.utc) - timedelta(minutes=15)
                        ).first()
                        if not last_alarm:
                            db.add(models.SystemLog(
                                device_id=latest_data.device_id,
                                level="critical",
                                message="Safety Lockout Active: 3 consecutive cycles completed without sufficient moisture rise. Holding motor OFF to prevent dry-run or overflow."
                            ))
                            db.commit()
                        print("[SAFETY LOCKOUT] 3 consecutive cycles completed. Holding motor OFF for 15 minutes.")
                        db.close()
                        await asyncio.sleep(5)
                        continue

                    # 6.4. SCHEDULE PUMP_ON
                    new_cmd = models.ControlCommand(
                        device_id=latest_data.device_id,
                        command_type="PUMP_ON",
                        status="PENDING"
                    )
                    db.add(new_cmd)

                    motor_log = models.MotorLog(
                        device_id=latest_data.device_id,
                        status="ON"
                    )
                    db.add(motor_log)

                    db.add(models.SystemLog(
                        device_id=latest_data.device_id,
                        level="success",
                        message=f"Automated Irrigation Started: Moisture {latest_data.soil_moisture:.1f}% < Target {dynamic_threshold:.1f}% (Demand: {water_pct}%)"
                    ))
                    db.commit()
                    print(f"Scheduled PUMP_ON for {latest_data.device_id} due to low moisture: {latest_data.soil_moisture:.2f}%")
                        
            db.close()
        except Exception as e:
            print(f"Control loop error: {e}")
            
        await asyncio.sleep(5) # Run every 5 seconds (Reduced from 60 for faster responsiveness)
