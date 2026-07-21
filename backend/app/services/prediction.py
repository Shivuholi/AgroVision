import math

def calculate_evapotranspiration(temp_c: float, humidity: float, wind_speed: float, solar_rad: float, kc: float = 1.0) -> dict:
    # Penman-Monteith heuristic: ET_c = K_c * ET_0
    # Calculate a base ET_0
    et_0 = (temp_c * 0.1) + (solar_rad * 0.01) + (wind_speed * 0.5) - (humidity * 0.05)
    et_0 = max(0.1, et_0) # Ensure ET_0 is positive
    
    et_c = kc * et_0
    
    return {
        "et_0": et_0,
        "et_c": et_c,
        "kc": kc
    }

def calculate_radiation(lux: float) -> float:
    """Convert Lux to Solar Radiation (W/m2)"""
    return lux * 0.0079

def calculate_ppfd(lux: float) -> float:
    """Convert Lux to Photosynthetic Photon Flux Density (PPFD)"""
    return lux * 0.0185

def calculate_dynamic_threshold(ppfd: float) -> float:
    """Calculate target moisture threshold based on light stress (Calibrated for Red Soil & Hackathon Demo).
    PPFD thresholds have been significantly lowered so you can trigger them indoors using a phone flashlight!"""
    if ppfd > 50:    # > 2700 Lux (Phone Flashlight close up)
        return 52.0  
    elif ppfd > 20:  # > 1080 Lux (Phone Flashlight from a distance)
        return 45.0  
    elif ppfd >= 5:  # > 270 Lux (Bright Room Lighting)
        return 35.0  
    else:            # < 270 Lux (Dim Room / Shadow)
        return 30.0  

def predict_moisture_drop(current_moisture: float, et_rate: float, hours_ahead: int = 24) -> float:
    # Predict the soil moisture after `hours_ahead` given the ET rate
    # Calibrated for Red Soil: 1 mm of ET drops moisture by ~0.8% (dries faster than generic soil)
    drop_per_day = et_rate * 0.8 
    drop_per_hour = drop_per_day / 24.0
    
    predicted_moisture = current_moisture - (drop_per_hour * hours_ahead)
    return max(0.0, predicted_moisture)
