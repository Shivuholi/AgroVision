from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import random
import time
from datetime import datetime, timedelta
import math

from ..database import get_db
from .. import models
from ..services.prediction import (
    calculate_evapotranspiration,
    predict_moisture_drop,
    calculate_dynamic_threshold,
    calculate_predictive_water_need
)

router = APIRouter(
    prefix="/api/weather",
    tags=["weather"],
)

_cached_weather = {
    "timestamp": 0,
    "data": None
}

@router.get("/forecast")
def get_weather_forecast():
    now = time.time()
    # Cache forecast for 60 seconds to keep readings stable during active demo
    if _cached_weather["data"] is not None and (now - _cached_weather["timestamp"] < 60):
        return {
            "status": "success",
            "data": _cached_weather["data"]
        }
        
    is_rainy = random.random() > 0.65
    p_rain = round(random.uniform(0.65, 0.90), 2) if is_rainy else round(random.uniform(0.05, 0.25), 2)
    hours_to_rain = round(random.uniform(2.0, 5.5), 1) if is_rainy else round(random.uniform(14.0, 22.0), 1)
    
    weather_data = {
        "temperature_c": round(random.uniform(24.0, 32.0), 1),
        "humidity_percent": round(random.uniform(55.0, 85.0) if is_rainy else random.uniform(40.0, 65.0), 1),
        "wind_speed_ms": round(random.uniform(1.2, 4.5), 1),
        "solar_radiation_wm2": round(random.uniform(150.0, 400.0) if is_rainy else random.uniform(450.0, 780.0), 1),
        "condition": "Rainy" if is_rainy else "Sunny",
        "rain_probability": p_rain,
        "hours_until_rain": hours_to_rain
    }
    
    _cached_weather["timestamp"] = now
    _cached_weather["data"] = weather_data
    
    return {
        "status": "success",
        "data": weather_data
    }

@router.get("/hourly")
def get_hourly_forecast():
    now = datetime.now()
    base_temp = 25.0
    amplitude = 10.0
    
    forecast = []
    for i in range(24):
        target_time = now + timedelta(hours=i)
        hour = target_time.hour
        
        # Sine wave for temp
        temp = base_temp + amplitude * math.sin((hour - 8) / 24 * 2 * math.pi)
        
        # Diurnal condition & rain probability
        is_day = 6 <= hour <= 18
        
        # Rain chance wave: higher afternoon/evening
        rain_prob = max(5, int(40 + 35 * math.sin((hour - 12) / 24 * 2 * math.pi)))
        if rain_prob > 60:
            condition = "Rain Showers" if is_day else "Rainy Night"
        elif is_day:
            condition = "Sunny" if rain_prob < 25 else "Cloudy"
        else:
            condition = "Clear Night" if rain_prob < 25 else "Cloudy Night"
            
        humidity = max(30.0, 100.0 - (temp * 1.5)) + random.uniform(-3, 3)
        
        forecast.append({
            "timestamp": target_time.isoformat(),
            "time_formatted": target_time.strftime("%I:%M %p"),
            "temperature_c": round(temp, 1),
            "humidity_percent": round(humidity, 1),
            "condition": condition,
            "rain_probability": rain_prob,
            "is_day": is_day
        })
        
    return {
        "status": "success",
        "data": forecast
    }

@router.get("/et_intelligence")
def get_et_intelligence():
    weather = get_weather_forecast()["data"]
    et_data = calculate_evapotranspiration(
        temp_c=weather["temperature_c"],
        humidity=weather["humidity_percent"],
        wind_speed=weather["wind_speed_ms"],
        solar_rad=weather["solar_radiation_wm2"],
        kc=1.2
    )
    
    return {
        "weather": weather,
        "et_breakdown": et_data
    }

@router.get("/water_recommendation")
def get_water_recommendation(device_id: str = "ESP32_01", db: Session = Depends(get_db)):
    weather = get_weather_forecast()["data"]
    
    # Query latest telemetry
    latest_data = db.query(models.SensorData).filter(
        models.SensorData.device_id == device_id
    ).order_by(models.SensorData.timestamp.desc()).first()
    
    soil_moisture = latest_data.soil_moisture if latest_data else 32.0
    ppfd = latest_data.ppfd if latest_data else 15.0
    dynamic_threshold = calculate_dynamic_threshold(ppfd)
    
    p_rain = weather.get("rain_probability", 0.70 if "Rain" in weather.get("condition", "") else 0.15)
    hours_to_rain = weather.get("hours_until_rain", 4.0 if "Rain" in weather.get("condition", "") else 20.0)
    
    water_calc = calculate_predictive_water_need(
        w_need=100.0,
        p_rain=p_rain,
        hours_until_rain=hours_to_rain,
        soil_moisture=soil_moisture,
        target_threshold=dynamic_threshold
    )
    
    return {
        "status": "success",
        "data": water_calc,
        "weather": weather
    }

