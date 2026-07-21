from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from .. import models, schemas
from ..database import get_db

router = APIRouter(
    prefix="/api/sensors",
    tags=["sensors"],
)

@router.post("/data", response_model=schemas.SensorDataResponse)
def create_sensor_data(data: schemas.SensorDataCreate, db: Session = Depends(get_db)):
    db_data = models.SensorData(**data.model_dump())
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data

@router.post("/telemetry", response_model=schemas.TelemetryResponse)
def create_telemetry_data(payload: schemas.TelemetryPayload, db: Session = Depends(get_db)):
    # Convert ESP32 payload to internal SensorData format
    db_data = models.SensorData(
        device_id="ESP32_01", # Assume a default device ID or get from headers
        temperature=payload.temperature,
        humidity=payload.humidity,
        soil_moisture=float(payload.moisture_percent),
        lux=float(payload.lux)
    )
    db.add(db_data)
    
    # Check if the pump should be ON based on the MotorLog
    # (The background control loop schedules this)
    active_motor = db.query(models.MotorLog).filter(
        models.MotorLog.device_id == "ESP32_01",
        models.MotorLog.status == "ON",
        models.MotorLog.end_time == None
    ).first()
    
    pump_on = True if active_motor else False

    db.commit()
    
    return {
        "status": "success",
        "pump_on": pump_on
    }

@router.get("/history", response_model=List[schemas.SensorDataResponse])
def get_sensor_history(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    data = db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).offset(skip).limit(limit).all()
    # Return reversed to have chronological order for charts
    return data[::-1]

@router.get("/latest", response_model=schemas.SensorDataResponse)
def get_latest_sensor_data(db: Session = Depends(get_db)):
    data = db.query(models.SensorData).order_by(models.SensorData.timestamp.desc()).first()
    if data is None:
        raise HTTPException(status_code=404, detail="No sensor data found")
    return data

@router.post("/nutrients", response_model=schemas.NutrientEntryResponse)
def create_nutrient_entry(data: schemas.NutrientEntryCreate, db: Session = Depends(get_db)):
    db_data = models.NutrientEntry(**data.model_dump())
    db.add(db_data)
    db.commit()
    db.refresh(db_data)
    return db_data

@router.get("/nutrients/latest", response_model=schemas.NutrientEntryResponse)
def get_latest_nutrients(db: Session = Depends(get_db)):
    data = db.query(models.NutrientEntry).order_by(models.NutrientEntry.timestamp.desc()).first()
    if data is None:
        raise HTTPException(status_code=404, detail="No manual nutrient data found")
    return data

@router.get("/logs", response_model=List[schemas.SystemLogResponse])
def get_system_logs(limit: int = 10, db: Session = Depends(get_db)):
    # Returns latest system logs
    return db.query(models.SystemLog).order_by(models.SystemLog.timestamp.desc()).limit(limit).all()

