import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from .. import models
from ..database import SessionLocal
from .prediction import calculate_evapotranspiration, predict_moisture_drop, calculate_dynamic_threshold
from ..routers.weather import get_weather_forecast

# The threshold is now dynamic based on Light Stress (PPFD)

async def run_control_loop():
    while True:
        try:
            db = SessionLocal()
            
            # 1. Get latest sensor data (assume 1 device for now: "ESP32_01")
            latest_data = db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).first()
            
            if latest_data:
                # 2. Get manual NPK entry
                latest_npk = db.query(models.NutrientEntry).order_by(models.NutrientEntry.timestamp.desc()).first()
                if latest_npk:
                    # Logic here might use NPK if needed, just logging for now
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
                
                # 5. Check against threshold
                # Changed to use actual current moisture for stable Hackathon Demo
                if latest_data.soil_moisture < dynamic_threshold:
                    # RAIN DELAY CHECK
                    weather_condition = weather.get("condition", "Unknown")
                    is_rainy = any(word in weather_condition.lower() for word in ["rain", "storm", "shower", "drizzle"])
                    
                    if is_rainy:
                        # Log the inhibition
                        last_rain_log = db.query(models.SystemLog).filter(
                            models.SystemLog.message.contains("Rain Delay"),
                            models.SystemLog.timestamp > datetime.now(timezone.utc) - timedelta(hours=1)
                        ).first()
                        
                        if not last_rain_log:
                            db.add(models.SystemLog(
                                device_id=latest_data.device_id,
                                level="warning",
                                message=f"Rain Delay: Predicted moisture {predicted_moisture:.1f}% is low, but weather is '{weather_condition}'. Skipping irrigation."
                            ))
                            db.commit()
                        print(f"Irrigation inhibited by Rain Delay. Condition: {weather_condition}")
                        db.close()
                        await asyncio.sleep(5) # Reduced for faster responsiveness
                        continue

                    # Check if motor is already ON
                    active_motor = db.query(models.MotorLog).filter(
                        models.MotorLog.device_id == latest_data.device_id,
                        models.MotorLog.status == "ON",
                        models.MotorLog.end_time == None
                    ).first()
                    
                    if not active_motor:
                        # Schedule watering
                        new_cmd = models.ControlCommand(
                            device_id=latest_data.device_id,
                            command_type="PUMP_ON",
                            status="PENDING"
                        )
                        db.add(new_cmd)
                        
                        # Add MotorLog immediately to sync with frontend
                        motor_log = models.MotorLog(
                            device_id=latest_data.device_id,
                            status="ON"
                        )
                        db.add(motor_log)
                        
                        db.add(models.SystemLog(
                            device_id=latest_data.device_id,
                            level="success",
                            message=f"Automated Irrigation Started: Moisture {latest_data.soil_moisture:.1f}% < Threshold {dynamic_threshold:.1f}%"
                        ))
                        
                        db.commit()
                        print(f"Scheduled PUMP_ON for {latest_data.device_id} due to low moisture: {latest_data.soil_moisture:.2f}%")
                        
                # 6. Check if motor needs to turn OFF (Safety Timeout & Hysteresis)
                active_motors = db.query(models.MotorLog).filter(
                    models.MotorLog.device_id == latest_data.device_id,
                    models.MotorLog.status == "ON",
                    models.MotorLog.end_time == None
                ).all()
                
                if active_motors:
                    for motor in active_motors:
                        motor_start = motor.start_time.replace(tzinfo=timezone.utc) if motor.start_time.tzinfo is None else motor.start_time
                        run_duration = (datetime.now(timezone.utc) - motor_start).total_seconds()
                        
                        # Turn off if soil is wet enough OR it's been running for > 15 seconds
                        if latest_data.soil_moisture > (dynamic_threshold + 5.0) or run_duration > 15:
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
                                message=f"Irrigation Stopped: Moisture {latest_data.soil_moisture:.1f}% (Runtime: {int(run_duration)}s)"
                            ))
                            db.commit()
                            print(f"Scheduled PUMP_OFF for {latest_data.device_id} (Runtime: {int(run_duration)}s)")
                        
            db.close()
        except Exception as e:
            print(f"Control loop error: {e}")
            
        await asyncio.sleep(5) # Run every 5 seconds (Reduced from 60 for faster responsiveness)
