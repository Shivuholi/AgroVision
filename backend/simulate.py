import time
import random
import httpx

API_URL = "http://localhost:8000/api/sensors/data"
DEVICE_ID = "ESP32_01"

def simulate_esp32():
    print(f"Starting simulation for {DEVICE_ID}...")
    
    # Initial state
    temp = 25.0
    hum = 60.0
    soil = 45.0
    
    while True:
        # Simulate slight random changes
        temp += random.uniform(-0.5, 0.5)
        hum += random.uniform(-1.0, 1.0)
        
        # Check if pump is running to simulate realistic soil hydration
        is_pumping = False
        try:
            runtime_resp = httpx.get(f"http://localhost:8000/api/control/runtime?device_id={DEVICE_ID}", timeout=1.5)
            if runtime_resp.status_code == 200:
                is_pumping = runtime_resp.json().get("is_on", False)
        except Exception:
            is_pumping = False

        if is_pumping:
            soil += random.uniform(3.0, 4.5)
            print(f"[WATERING ACTIVE] Pump is ON! Soil moisture rising: {soil:.1f}%")
        else:
            # Soil moisture drops slowly when pump is idle
            soil_drop = 0.35 if temp > 30 else 0.15
            soil -= random.uniform(soil_drop - 0.05, soil_drop + 0.1)
        
        # Ensure bounds
        temp = max(10, min(temp, 45))
        hum = max(20, min(hum, 90))
        soil = max(0, min(soil, 100))
        
        payload = {
            "device_id": DEVICE_ID,
            "temperature": temp,
            "humidity": hum,
            "soil_moisture": soil
        }
        
        try:
            response = httpx.post(API_URL, json=payload)
            if response.status_code == 200:
                print(f"Data pushed: Temp {temp:.1f}C, Soil {soil:.1f}%")
            else:
                print(f"Error pushing data: {response.text}")
        except Exception as e:
            print(f"Connection error: {e}")
            
        time.sleep(5) # Push every 5 seconds for fast demo

if __name__ == "__main__":
    simulate_esp32()
