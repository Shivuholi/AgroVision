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
        
        # Soil moisture drops slowly, but drops faster if temp is high
        soil_drop = 0.5 if temp > 30 else 0.2
        soil -= random.uniform(soil_drop - 0.1, soil_drop + 0.2)
        
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
