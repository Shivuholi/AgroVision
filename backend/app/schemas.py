from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class SensorDataCreate(BaseModel):
    device_id: str
    temperature: float
    humidity: float
    soil_moisture: float
    lux: Optional[float] = 0.0

class TelemetryPayload(BaseModel):
    temperature: float
    humidity: float
    moisture_percent: float
    lux: float

class TelemetryResponse(BaseModel):
    status: str
    pump_on: bool

class NutrientEntryCreate(BaseModel):
    npk_n: float
    npk_p: float
    npk_k: float

class NutrientEntryResponse(NutrientEntryCreate):
    id: int
    timestamp: datetime

    class Config:
        from_attributes = True

class SensorDataResponse(SensorDataCreate):
    id: int
    timestamp: datetime
    solar_radiation: float
    ppfd: float

    class Config:
        from_attributes = True

class ControlCommandCreate(BaseModel):
    device_id: str
    command_type: str

class ControlCommandResponse(ControlCommandCreate):
    id: int
    timestamp: datetime
    status: str

    class Config:
        from_attributes = True

class SystemLogResponse(BaseModel):
    id: int
    timestamp: datetime
    device_id: str
    level: str
    message: str

    class Config:
        from_attributes = True
