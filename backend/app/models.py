from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Float, DateTime
from sqlalchemy.sql import func
from .database import Base

class SensorData(Base):
    __tablename__ = "sensor_data"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    device_id = Column(String, index=True)
    temperature = Column(Float)
    humidity = Column(Float)
    soil_moisture = Column(Float)
    lux = Column(Float, nullable=True, default=0.0)

    @property
    def solar_radiation(self) -> float:
        return self.lux * 0.0079 if self.lux else 0.0

    @property
    def ppfd(self) -> float:
        return self.lux * 0.0185 if self.lux else 0.0

class NutrientEntry(Base):
    __tablename__ = "nutrient_entries"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    npk_n = Column(Float)
    npk_p = Column(Float)
    npk_k = Column(Float)

class ControlCommand(Base):
    __tablename__ = "control_commands"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    device_id = Column(String, index=True)
    command_type = Column(String) # e.g. "PUMP_ON", "PUMP_OFF"
    status = Column(String, default="PENDING") # PENDING, EXECUTED

class MotorLog(Base):
    __tablename__ = "motor_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    status = Column(String) # "ON" or "OFF"
    start_time = Column(DateTime(timezone=True), server_default=func.now())
    end_time = Column(DateTime(timezone=True), nullable=True)

class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    device_id = Column(String, index=True)
    level = Column(String) # "info", "warning", "success", "critical"
    message = Column(String)

