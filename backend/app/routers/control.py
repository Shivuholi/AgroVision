from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/api/control",
    tags=["control"],
)

@router.get("/schedule", response_model=List[schemas.ControlCommandResponse])
def get_pending_commands(device_id: str, db: Session = Depends(get_db)):
    commands = db.query(models.ControlCommand).filter(
        models.ControlCommand.device_id == device_id,
        models.ControlCommand.status == "PENDING"
    ).all()
    
    # Mark as executed once fetched by the device
    for cmd in commands:
        cmd.status = "EXECUTED"
    db.commit()
    
    return commands

@router.post("/command", response_model=schemas.ControlCommandResponse)
def create_command(cmd: schemas.ControlCommandCreate, db: Session = Depends(get_db)):
    db_cmd = models.ControlCommand(**cmd.model_dump())
    db.add(db_cmd)
    db.commit()
    db.refresh(db_cmd)
    return db_cmd

from datetime import datetime, timezone, timedelta
from sqlalchemy import func
from ..services.prediction import calculate_dynamic_threshold, calculate_predictive_water_need
from .weather import get_weather_forecast

@router.get("/runtime")
def get_motor_runtime(device_id: str, db: Session = Depends(get_db)):
    # Calculate Total Runtime Today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    logs_today = db.query(models.MotorLog).filter(
        models.MotorLog.device_id == device_id,
        models.MotorLog.start_time >= today_start
    ).all()
    
    total_seconds_today = 0
    current_runtime_seconds = 0
    is_on = False
    
    for log in logs_today:
        start = log.start_time.replace(tzinfo=timezone.utc) if log.start_time.tzinfo is None else log.start_time
        if log.status == "ON":
            if log.end_time:
                end = log.end_time.replace(tzinfo=timezone.utc) if log.end_time.tzinfo is None else log.end_time
                total_seconds_today += (end - start).total_seconds()
            else:
                # Motor is currently running
                is_on = True
                now = datetime.now(timezone.utc)
                current_runtime_seconds = (now - start).total_seconds()
                total_seconds_today += current_runtime_seconds

    # Biological Rules
    # Pump dispenses 100 grams of water per second of runtime
    total_water_pumped_grams = total_seconds_today * 100
    # 1 gram of dry plant matter requires 500 grams of water
    estimated_biomass_grams = total_water_pumped_grams / 500

    # Get latest PPFD for dynamic threshold
    latest_data = db.query(models.SensorData).filter(models.SensorData.device_id == device_id).order_by(models.SensorData.timestamp.desc()).first()
    dynamic_threshold = 30.0 # Default fallback
    soil_moisture = 32.0
    if latest_data:
        dynamic_threshold = calculate_dynamic_threshold(latest_data.ppfd)
        soil_moisture = latest_data.soil_moisture

    # Calculate Predictive Water Need (W_now formula)
    weather = get_weather_forecast()["data"]
    p_rain = weather.get("rain_probability", 0.70 if "Rain" in weather.get("condition", "") else 0.15)
    hours_to_rain = weather.get("hours_until_rain", 4.0 if "Rain" in weather.get("condition", "") else 20.0)

    water_calc = calculate_predictive_water_need(
        w_need=100.0,
        p_rain=p_rain,
        hours_until_rain=hours_to_rain,
        soil_moisture=soil_moisture,
        target_threshold=dynamic_threshold
    )

    # Safety: Auto-cleanup stale running logs if motor has been running > 25 seconds
    if is_on and current_runtime_seconds > 25:
        open_motor = db.query(models.MotorLog).filter(
            models.MotorLog.device_id == device_id,
            models.MotorLog.status == "ON",
            models.MotorLog.end_time == None
        ).first()
        if open_motor:
            open_motor.end_time = datetime.now(timezone.utc)
            db.commit()
            is_on = False
            current_runtime_seconds = 0

    # Calculate Soak Cooldown Remaining
    COOLDOWN_SOAK_SECONDS = 60
    cooldown_remaining_seconds = 0

    last_finished_motor = db.query(models.MotorLog).filter(
        models.MotorLog.device_id == device_id,
        models.MotorLog.status == "ON",
        models.MotorLog.end_time != None
    ).order_by(models.MotorLog.end_time.desc()).first()

    if last_finished_motor and last_finished_motor.end_time and not is_on:
        end_time_utc = last_finished_motor.end_time.replace(tzinfo=timezone.utc) if last_finished_motor.end_time.tzinfo is None else last_finished_motor.end_time
        time_since_off = (datetime.now(timezone.utc) - end_time_utc).total_seconds()
        if time_since_off < COOLDOWN_SOAK_SECONDS:
            cooldown_remaining_seconds = int(COOLDOWN_SOAK_SECONDS - time_since_off)

    if is_on:
        state_status = "RUNNING"
    elif cooldown_remaining_seconds > 0:
        state_status = f"SOAK HOLD ({cooldown_remaining_seconds}s)"
    else:
        state_status = "STANDBY"

    return {
        "is_on": is_on,
        "current_runtime_seconds": int(current_runtime_seconds),
        "total_runtime_today_seconds": int(total_seconds_today),
        "total_water_pumped_grams": int(total_water_pumped_grams),
        "estimated_biomass_grams": int(estimated_biomass_grams),
        "dynamic_threshold": float(dynamic_threshold),
        "water_need": water_calc,
        "cooldown_remaining_seconds": cooldown_remaining_seconds,
        "state_status": state_status
    }


