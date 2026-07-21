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
from ..services.prediction import calculate_dynamic_threshold

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
    if latest_data:
        dynamic_threshold = calculate_dynamic_threshold(latest_data.ppfd)

    return {
        "is_on": is_on,
        "current_runtime_seconds": int(current_runtime_seconds),
        "total_runtime_today_seconds": int(total_seconds_today),
        "total_water_pumped_grams": int(total_water_pumped_grams),
        "estimated_biomass_grams": int(estimated_biomass_grams),
        "dynamic_threshold": float(dynamic_threshold)
    }

