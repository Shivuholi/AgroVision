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
    """Calculate dynamic target moisture threshold continuously based on light stress (PPFD):
    Target Threshold = 30% + (PPFD / 1000 * 22%)
    Bounded: 30.0% (baseline/night) to 52.0% (peak solar stress)."""
    if ppfd is None:
        ppfd = 0.0
    threshold = 30.0 + (ppfd / 1000.0) * 22.0
    return round(max(30.0, min(52.0, threshold)), 1)

def predict_moisture_drop(current_moisture: float, et_rate: float, hours_ahead: int = 24) -> float:
    # Predict the soil moisture after `hours_ahead` given the ET rate
    # Calibrated for Red Soil: 1 mm of ET drops moisture by ~0.8% (dries faster than generic soil)
    drop_per_day = et_rate * 0.8 
    drop_per_hour = drop_per_day / 24.0
    
    predicted_moisture = current_moisture - (drop_per_hour * hours_ahead)
    return max(0.0, predicted_moisture)

def get_rain_certainty(hours_until_rain: float) -> float:
    """Certainty coefficient C_rain based on time until rain.
    Within 0–6 hours: 1.0 (Highly certain)
    6–12 hours: 0.75 (Moderately certain)
    12–24 hours: 0.50 (Less certain)
    > 24 hours: 0.0 (Beyond current irrigation window)"""
    if hours_until_rain <= 6.0:
        return 1.0
    elif hours_until_rain <= 12.0:
        return 0.75
    elif hours_until_rain <= 24.0:
        return 0.50
    else:
        return 0.0

def get_stress_modifier(soil_moisture: float, target_threshold: float = 40.0) -> float:
    """Plant stress modifier M_stress:
    Bone dry / Severe wilting (< 25%): 1.2 (Needs an extra buffer)
    Slightly dry / Normal (< target_threshold): 1.0
    Still damp (>= target_threshold): 0.0 (Do not water at all)"""
    if soil_moisture < 25.0:
        return 1.2
    elif soil_moisture < target_threshold:
        return 1.0
    else:
        return 0.0

def calculate_predictive_water_need(
    w_need: float = 100.0,
    p_rain: float = 0.0,
    hours_until_rain: float = 24.0,
    soil_moisture: float = 30.0,
    target_threshold: float = 40.0
) -> dict:
    """Calculates water need percentage according to:
    W_now = W_need * (1 - P_rain * C_rain) * M_stress"""
    c_rain = get_rain_certainty(hours_until_rain)
    m_stress = get_stress_modifier(soil_moisture, target_threshold)
    
    # Rain reduction factor (bounded between 0.0 and 1.0)
    rain_reduction_factor = max(0.0, min(1.0, 1.0 - (p_rain * c_rain)))
    
    # Calculate W_now
    w_now = w_need * rain_reduction_factor * m_stress
    percentage = (w_now / w_need) * 100.0 if w_need > 0 else 0.0
    
    if m_stress == 0.0:
        status_label = "Soil Damp - No Irrigation Needed"
    elif rain_reduction_factor == 0.0:
        status_label = "Rain Imminent - Irrigation Canceled"
    elif m_stress > 1.0:
        status_label = "Severe Stress Buffer Active (1.2x)"
    elif rain_reduction_factor < 1.0:
        discount_pct = int(round((1.0 - rain_reduction_factor) * 100))
        status_label = f"Rain Discount Active (-{discount_pct}%)"
    else:
        status_label = "Standard Irrigation Demand"

    return {
        "w_now": round(w_now, 2),
        "w_need": round(w_need, 2),
        "percentage": round(percentage, 1),
        "p_rain": round(p_rain, 2),
        "c_rain": round(c_rain, 2),
        "m_stress": round(m_stress, 2),
        "rain_reduction_factor": round(rain_reduction_factor, 2),
        "status_label": status_label,
        "hours_until_rain": round(hours_until_rain, 1),
        "soil_moisture": round(soil_moisture, 1),
        "target_threshold": round(target_threshold, 1)
    }

