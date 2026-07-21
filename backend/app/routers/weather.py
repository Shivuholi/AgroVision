from fastapi import APIRouter
import random

router = APIRouter(
    prefix="/api/weather",
    tags=["weather"],
)

@router.get("/forecast")
def get_weather_forecast():
    # Mocked weather forecast since no API key is provided
    return {
        "status": "success",
        "data": {
            "temperature_c": random.uniform(20.0, 35.0),
            "humidity_percent": random.uniform(40.0, 80.0),
            "wind_speed_ms": random.uniform(1.0, 5.0),
            "solar_radiation_wm2": random.uniform(200.0, 800.0), # Needed for ET calculation
            "condition": "Rainy" if random.random() > 0.7 else "Sunny"
        }
    }

from datetime import datetime, timedelta
import math

@router.get("/hourly")
def get_hourly_forecast():
    # Generate 24 hours of smart mock data simulating a diurnal cycle
    now = datetime.now()
    # Let's say peak temp is at 14:00 (2 PM) and lowest is at 02:00 (2 AM)
    base_temp = 25.0
    amplitude = 10.0
    
    forecast = []
    for i in range(24):
        target_time = now + timedelta(hours=i)
        hour = target_time.hour
        
        # Sine wave: shift by 8 hours so minimum is at 2 AM
        # formula: temp = base + amp * sin((hour - 8) / 24 * 2pi)
        temp = base_temp + amplitude * math.sin((hour - 8) / 24 * 2 * math.pi)
        
        # Determine condition and icon
        is_day = 6 <= hour <= 18
        if is_day:
            condition = "Sunny" if random.random() > 0.3 else "Cloudy"
        else:
            condition = "Clear Night" if random.random() > 0.3 else "Cloudy Night"
            
        humidity = max(30.0, 100.0 - (temp * 1.5)) + random.uniform(-5, 5)
        
        forecast.append({
            "timestamp": target_time.isoformat(),
            "time_formatted": target_time.strftime("%I:%M %p"),
            "temperature_c": round(temp, 1),
            "humidity_percent": round(humidity, 1),
            "condition": condition,
            "is_day": is_day
        })
        
    return {
        "status": "success",
        "data": forecast
    }

from ..services.prediction import calculate_evapotranspiration, predict_moisture_drop

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
