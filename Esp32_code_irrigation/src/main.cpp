#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <BH1750.h>
#include <DHT.h>

// ==========================================
// 1. PIN CONFIGURATION (ESP32 DevKit V1)
// ==========================================
#define DHT_PIN         4        // DHT11 / DHT22 Data pin -> GPIO 4
#define DHT_TYPE        DHT11    // Change to DHT22 if using white sensor
#define SOIL_PIN        34       // Capacitive Soil Moisture (Analog) -> GPIO 34 (ADC1_CH6, safe with Wi-Fi)
#define I2C_SDA_PIN     21       // BH1750 SDA -> GPIO 21
#define I2C_SCL_PIN     22       // BH1750 SCL -> GPIO 22

// Visual Indicator without relay: ESP32 DevKit V1 has a built-in Blue LED on GPIO 2!
// It will turn ON when the server orders the pump to run, and turn OFF when idle.
#define ONBOARD_LED     2        
#define RELAY_PIN       26       // Optional: GPIO 26 (kept ready for when you connect the relay later)
#define RELAY_ON        LOW      // Active-LOW relay logic
#define RELAY_OFF       HIGH

// Set to true only when you physically connect the relay module to GPIO 26
const bool ENABLE_RELAY = false; 

// ==========================================
// 2. SOIL SENSOR CALIBRATION (12-bit ADC: 0 - 4095)
// ==========================================
// In air (completely dry) ~ 3000-3400; in water ~ 1200-1500
const int SOIL_AIR_VALUE   = 3200; 
const int SOIL_WATER_VALUE = 1400; 

// ==========================================
// 3. NETWORK & BACKEND CONFIGURATION
// ==========================================
const char* ssid     = "galaxy_A26";
const char* password = "12345678";

// Replace with your computer's local IP address (e.g., http://192.168.1.105:8000/api/sensors/telemetry)
const char* serverUrl = "http://10.228.79.62:8000/api/sensors/telemetry";

// Telemetry interval (milliseconds)
const unsigned long timerDelay = 5000;
unsigned long lastTime = 0;

// Hardware instances
DHT dht(DHT_PIN, DHT_TYPE);
BH1750 lightMeter;
bool bh1750Ready = false;

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println("\n==========================================");
  Serial.println("  AgroVision ESP32 Node Booting (Sensor Mode)");
  Serial.println("  (Onboard LED GPIO 2 indicates Pump Status)");
  Serial.println("==========================================");

  // Setup Visual LED Indicator
  pinMode(ONBOARD_LED, OUTPUT);
  digitalWrite(ONBOARD_LED, LOW);

  // Setup Relay Pin (if connected later)
  if (ENABLE_RELAY) {
    pinMode(RELAY_PIN, OUTPUT);
    digitalWrite(RELAY_PIN, RELAY_OFF);
  }

  // Initialize I2C and BH1750 Light Sensor
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println("[OK] BH1750 Light Sensor detected.");
    bh1750Ready = true;
  } else {
    Serial.println("[WARN] BH1750 not detected. Check SDA(21), SCL(22).");
  }

  // Initialize DHT Sensor
  dht.begin();
  Serial.println("[OK] DHT Sensor initialized.");

  // Configure ADC resolution (12-bit: 0 - 4095)
  analogReadResolution(12);

  // Connect to Wi-Fi
  Serial.printf("Connecting to Wi-Fi '%s'...", ssid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Connected to Wi-Fi!");
    Serial.print("ESP32 IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WARN] Wi-Fi connection timed out. Retrying in loop.");
  }
}

// Helper: Read soil moisture with 5-sample smoothing
float readSoilMoisturePercent() {
  long sum = 0;
  for (int i = 0; i < 5; i++) {
    sum += analogRead(SOIL_PIN);
    delay(10);
  }
  int rawAdc = sum / 5;
  
  rawAdc = constrain(rawAdc, min(SOIL_WATER_VALUE, SOIL_AIR_VALUE), max(SOIL_WATER_VALUE, SOIL_AIR_VALUE));
  float moisture = map(rawAdc, SOIL_AIR_VALUE, SOIL_WATER_VALUE, 0, 100);
  return constrain(moisture, 0.0f, 100.0f);
}

void loop() {
  // Push telemetry every 5 seconds
  if ((millis() - lastTime) > timerDelay) {
    lastTime = millis();

    if (WiFi.status() == WL_CONNECTED) {
      // ----------------------------------------
      // 1. Read Real Sensors
      // ----------------------------------------
      float temp = dht.readTemperature();
      float hum  = dht.readHumidity();
      float soil = readSoilMoisturePercent();
      
      float lux = 0.0;
      if (bh1750Ready) {
        lux = lightMeter.readLightLevel();
      }

      // Check if DHT reading is valid
      if (isnan(temp) || isnan(hum)) {
        Serial.println("[WARN] DHT reading timed out. Using fallback defaults.");
        temp = 26.0;
        hum  = 60.0;
      }

      Serial.printf("\n[Telemetry] Temp: %.1f C | Hum: %.1f %% | Soil: %.1f %% | Lux: %.1f lx\n",
                    temp, hum, soil, lux);

      // ----------------------------------------
      // 2. Build JSON Payload (ArduinoJson v7 syntax)
      // ----------------------------------------
      JsonDocument doc;
      doc["temperature"]      = round(temp * 10.0) / 10.0;
      doc["humidity"]         = round(hum * 10.0) / 10.0;
      doc["moisture_percent"] = round(soil);
      doc["lux"]              = round(lux);

      String requestBody;
      serializeJson(doc, requestBody);

      // ----------------------------------------
      // 3. Send HTTP POST to FastAPI
      // ----------------------------------------
      HTTPClient http;
      http.begin(serverUrl);
      http.setTimeout(5000); // 5 second timeout
      http.setReuse(false);
      http.addHeader("Content-Type", "application/json");

      int httpResponseCode = http.POST(requestBody);

      // ----------------------------------------
      // 4. Handle Server Response & Visual Indicator
      // ----------------------------------------
      if (httpResponseCode == 200) {
        String responsePayload = http.getString();
        
        JsonDocument resDoc;
        DeserializationError error = deserializeJson(resDoc, responsePayload);

        if (!error) {
          bool pumpOn = resDoc["pump_on"] | false;
          
          if (pumpOn) {
            // Visual indicator: Turn ON Blue Built-in LED on GPIO 2
            digitalWrite(ONBOARD_LED, HIGH);
            if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_ON);
            Serial.println("[STATUS] >>> PUMP DEMAND: ON (Blue Onboard LED is LIT) <<<");
          } else {
            // Visual indicator: Turn OFF Blue Built-in LED on GPIO 2
            digitalWrite(ONBOARD_LED, LOW);
            if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_OFF);
            Serial.println("[STATUS] Pump Demand: OFF (Blue Onboard LED is OFF)");
          }
        } else {
          Serial.println("[ERROR] Failed to parse backend JSON response.");
        }
      } else {
        Serial.printf("[HTTP ERROR] Status: %d (%s)\n", httpResponseCode, http.errorToString(httpResponseCode).c_str());
      }

      http.end();
    } else {
      Serial.println("[NET] Wi-Fi disconnected. Reconnecting...");
      WiFi.reconnect();
      digitalWrite(ONBOARD_LED, LOW);
      if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_OFF);
    }
  }
}
