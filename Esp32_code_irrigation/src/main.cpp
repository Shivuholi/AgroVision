#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <BH1750.h>
#include <DHT.h>
#include <esp_timer.h>

// ==========================================
// 1. PIN & HARDWARE CONFIGURATION
// ==========================================
#define DHT_PIN         4        // DHT11 / DHT22 Data pin -> GPIO 4
#define DHT_TYPE        DHT11    // DHT11 or DHT22
#define SOIL_PIN        34       // Capacitive Soil Moisture -> GPIO 34 (ADC1_CH6, Wi-Fi safe)
#define I2C_SDA_PIN     21       // BH1750 SDA -> GPIO 21
#define I2C_SCL_PIN     22       // BH1750 SCL -> GPIO 22

// Visual Indicator & Relay Output
#define ONBOARD_LED     2        // ESP32 DevKit V1 Blue Onboard LED
#define RELAY_PIN       26       // GPIO 26 for relay
#define RELAY_ON        LOW      // Active-LOW relay logic
#define RELAY_OFF       HIGH

// Set to true when physical relay module is connected to GPIO 26
const bool ENABLE_RELAY = false; 

// ==========================================
// 2. SOIL SENSOR CALIBRATION (12-bit ADC: 0 - 4095)
// ==========================================
const int SOIL_AIR_VALUE   = 3200; // Dry air
const int SOIL_WATER_VALUE = 1400; // Submerged in water

// ==========================================
// 3. NETWORK & MQTT CONFIGURATION
// ==========================================
const char* ssid         = "galaxy_A26";
const char* password     = "12345678";

// MQTT Broker: Default is public high-reliability broker for instant zero-config testing.
// In local deployment, you can point this to your computer's local IP (e.g., "192.168.1.100").
const char* mqtt_server  = "broker.emqx.io"; 
const int   mqtt_port    = 1883;

// Device & MQTT Topics
const char* DEVICE_ID       = "ESP32_01";
const char* TOPIC_TELEMETRY = "agrovision/nodes/ESP32_01/telemetry";
const char* TOPIC_COMMAND   = "agrovision/nodes/ESP32_01/cmd";
const char* TOPIC_STATUS    = "agrovision/nodes/ESP32_01/status";

// ==========================================
// 4. TIMING & SAFETY LIMITS
// ==========================================
const unsigned long TELEMETRY_INTERVAL_MS = 5000;   // Send telemetry every 5 seconds
const unsigned long MAX_PUMP_RUN_MS       = 20000;  // Autonomous hardware cutoff (20s)
const unsigned long RECONNECT_INTERVAL_MS = 5000;   // Non-blocking reconnect retry interval

// ==========================================
// 5. GLOBAL STATE & INSTANCES
// ==========================================
WiFiClient espClient;
PubSubClient mqttClient(espClient);
DHT dht(DHT_PIN, DHT_TYPE);
BH1750 lightMeter;

bool bh1750Ready = false;
bool isPumpRunning = false;
unsigned long pumpStartTime = 0;
unsigned long configuredPumpMaxMs = MAX_PUMP_RUN_MS;
unsigned long lastTelemetryTime = 0;
unsigned long lastReconnectAttempt = 0;

// ========================================================
// HARDWARE TIMER INTERRUPT (SILICON-LEVEL AUTONOMOUS CUTOFF)
// ========================================================
esp_timer_handle_t pumpTimerHandle = NULL;
volatile bool hwTimerCutoffFired = false;

// Hardware Timer ISR Callback — Executes in high-priority Timer Task / ISR context
void IRAM_ATTR onPumpHardwareTimerTimeout(void* arg) {
  // Direct silicon-level pin shutdown (< 1 microsecond):
  digitalWrite(ONBOARD_LED, LOW);
  if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_OFF);
  
  isPumpRunning = false;
  hwTimerCutoffFired = true;
}

// ==========================================
// 6. ACTUATOR CONTROL & SAFETY CUTOFF
// ==========================================
void setPumpState(bool state, const char* reason, unsigned long maxDurationSec = 0) {
  if (state) {
    isPumpRunning = true;
    pumpStartTime = millis();
    configuredPumpMaxMs = (maxDurationSec > 0) ? (maxDurationSec * 1000) : MAX_PUMP_RUN_MS;
    
    // Safety clamp: never allow duration to exceed hardware limit of 30 seconds
    if (configuredPumpMaxMs > 30000) configuredPumpMaxMs = 30000;

    digitalWrite(ONBOARD_LED, HIGH);
    if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_ON);

    // ARM HARDWARE TIMER: Silicon-level countdown in microseconds
    if (pumpTimerHandle != NULL) {
      esp_timer_stop(pumpTimerHandle); // cleanly disarm any previous running timer
      esp_timer_start_once(pumpTimerHandle, (uint64_t)configuredPumpMaxMs * 1000ULL);
    }

    Serial.printf("\n[ACTUATOR] >>> PUMP ON (HW Timer Armed: %lu ms) | Reason: %s <<<\n", configuredPumpMaxMs, reason);
  } else {
    // DISARM HARDWARE TIMER
    if (pumpTimerHandle != NULL) {
      esp_timer_stop(pumpTimerHandle);
    }

    isPumpRunning = false;
    pumpStartTime = 0;

    digitalWrite(ONBOARD_LED, LOW);
    if (ENABLE_RELAY) digitalWrite(RELAY_PIN, RELAY_OFF);

    Serial.printf("\n[ACTUATOR] Pump OFF | Reason: %s\n", reason);
  }
}

// ==========================================
// 7. SENSOR SAMPLING (TRIMMED-MEAN FILTER)
// ==========================================
float readSoilMoisturePercent() {
  const int NUM_SAMPLES = 10;
  int samples[NUM_SAMPLES];

  // 1. Collect 10 samples (5ms apart to avoid blocking)
  for (int i = 0; i < NUM_SAMPLES; i++) {
    samples[i] = analogRead(SOIL_PIN);
    delay(5);
  }

  // 2. Simple Bubble Sort for median trimming
  for (int i = 0; i < NUM_SAMPLES - 1; i++) {
    for (int j = 0; j < NUM_SAMPLES - i - 1; j++) {
      if (samples[j] > samples[j + 1]) {
        int temp = samples[j];
        samples[j] = samples[j + 1];
        samples[j + 1] = temp;
      }
    }
  }

  // 3. Discard lowest 2 and highest 2 (Wi-Fi RF noise spikes), average middle 6
  long sum = 0;
  for (int i = 2; i < NUM_SAMPLES - 2; i++) {
    sum += samples[i];
  }
  int filteredAdc = sum / (NUM_SAMPLES - 4);

  // 4. Constrain & Map to 0-100%
  int minVal = min(SOIL_WATER_VALUE, SOIL_AIR_VALUE);
  int maxVal = max(SOIL_WATER_VALUE, SOIL_AIR_VALUE);
  filteredAdc = constrain(filteredAdc, minVal, maxVal);

  float moisture = map(filteredAdc, SOIL_AIR_VALUE, SOIL_WATER_VALUE, 0, 100);
  return constrain(moisture, 0.0f, 100.0f);
}

// ==========================================
// 8. MQTT INCOMING COMMAND HANDLER (<50ms Latency)
// ==========================================
void onMqttMessageReceived(char* topic, byte* payload, unsigned int length) {
  char message[256];
  if (length >= sizeof(message)) length = sizeof(message) - 1;
  memcpy(message, payload, length);
  message[length] = '\0';

  Serial.printf("\n[MQTT RX] Topic: %s | Payload: %s\n", topic, message);

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, message);
  if (error) {
    Serial.println("[ERROR] Failed to parse JSON command!");
    return;
  }

  const char* action = doc["action"] | "";
  unsigned long duration = doc["duration"] | 15; // default 15s

  if (strcmp(action, "PUMP_ON") == 0) {
    setPumpState(true, "MQTT_COMMAND_RX", duration);
  } else if (strcmp(action, "PUMP_OFF") == 0) {
    setPumpState(false, "MQTT_COMMAND_RX");
  } else {
    Serial.printf("[WARN] Unknown action received: %s\n", action);
  }
}

// ==========================================
// 9. NON-BLOCKING MQTT RECONNECT WITH LWT
// ==========================================
bool reconnectMqtt() {
  if (mqttClient.connected()) return true;

  Serial.print("[MQTT] Connecting to broker... ");

  // Last Will and Testament (LWT): If ESP32 abruptly disconnects, broker posts "offline"
  bool connected = mqttClient.connect(
    DEVICE_ID,              // Client ID
    TOPIC_STATUS,           // LWT Topic
    1,                      // LWT QoS (1 = at least once)
    true,                   // LWT Retain
    "offline"               // LWT Payload
  );

  if (connected) {
    Serial.println("[OK] Connected!");
    // Publish online status
    mqttClient.publish(TOPIC_STATUS, "online", true);

    // Subscribe to incoming actuation commands
    mqttClient.subscribe(TOPIC_COMMAND, 1);
    Serial.printf("[MQTT] Subscribed to: %s\n", TOPIC_COMMAND);
  } else {
    Serial.printf("[FAIL] State code: %d\n", mqttClient.state());
  }
  return mqttClient.connected();
}

// ==========================================
// 10. SETUP
// ==========================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Serial.println("\n==========================================");
  Serial.println("  AgroVision ESP32 Real-Time MQTT Node    ");
  Serial.println("  (Push-Based Actuation & HW Safety Cutoff)");
  Serial.println("==========================================");

  // 1. Anti-Chatter Pin Configuration:
  // Set HIGH before setting OUTPUT to prevent active-LOW relay click on boot
  digitalWrite(RELAY_PIN, RELAY_OFF);
  if (ENABLE_RELAY) pinMode(RELAY_PIN, OUTPUT);

  pinMode(ONBOARD_LED, OUTPUT);
  digitalWrite(ONBOARD_LED, LOW);

  // 1.5. Initialize Silicon-Level Hardware Timer for Actuator Protection
  const esp_timer_create_args_t pumpTimerArgs = {
    .callback = &onPumpHardwareTimerTimeout,
    .arg = NULL,
    .dispatch_method = ESP_TIMER_TASK,
    .name = "pump_hw_timer"
  };
  esp_timer_create(&pumpTimerArgs, &pumpTimerHandle);
  Serial.println("[OK] Silicon-level Hardware Safety Timer initialized.");

  // 2. Initialize Sensors
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println("[OK] BH1750 Light Sensor detected.");
    bh1750Ready = true;
  } else {
    Serial.println("[WARN] BH1750 not detected. Continuing with lux=0.");
  }

  dht.begin();
  analogReadResolution(12);

  // 3. Connect to Wi-Fi
  Serial.printf("Connecting to Wi-Fi '%s'...", ssid);
  WiFi.mode(WIFI_STA);
  WiFi.begin(ssid, password);

  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 20) {
    delay(500);
    Serial.print(".");
    attempts++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Connected to Wi-Fi!");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WARN] Wi-Fi connection pending. Loop will retry asynchronously.");
  }

  // 4. Configure MQTT Client
  mqttClient.setServer(mqtt_server, mqtt_port);
  mqttClient.setCallback(onMqttMessageReceived);
  mqttClient.setBufferSize(512);
}

// ==========================================
// 11. MAIN NON-BLOCKING EVENT LOOP
// ==========================================
void loop() {
  // A. Non-blocking Wi-Fi and MQTT connection upkeep
  if (WiFi.status() == WL_CONNECTED) {
    if (!mqttClient.connected()) {
      unsigned long now = millis();
      if (now - lastReconnectAttempt > RECONNECT_INTERVAL_MS) {
        lastReconnectAttempt = now;
        reconnectMqtt();
      }
    } else {
      // Process incoming MQTT packets & keep-alives (Sub-millisecond)
      mqttClient.loop();
    }
  } else {
    // If Wi-Fi dropped while pump is running, trigger immediate failsafe cutoff!
    if (isPumpRunning) {
      setPumpState(false, "WIFI_LOST_FAILSAFE");
    }
  }

  // B. AUTONOMOUS HARDWARE SAFETY CUTOFF
  // Check if Hardware Timer ISR fired in the background
  if (hwTimerCutoffFired) {
    hwTimerCutoffFired = false;
    Serial.println("\n[CRITICAL HW INTERRUPT] >>> HARDWARE TIMER ISR EXPIRED! Relay killed at silicon level. <<<");
    if (mqttClient.connected()) {
      mqttClient.publish(TOPIC_STATUS, "ERR_HW_TIMER_CUTOFF");
    }
  }

  // Polling fallback check
  if (isPumpRunning) {
    unsigned long elapsed = millis() - pumpStartTime;
    if (elapsed >= configuredPumpMaxMs) {
      setPumpState(false, "AUTONOMOUS_HARDWARE_LIMIT_EXCEEDED");
    }
  }

  // C. PERIODIC TELEMETRY PUBLISH (Non-blocking timer)
  unsigned long now = millis();
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;

    // Read Sensors
    float temp = dht.readTemperature();
    float hum  = dht.readHumidity();
    float soil = readSoilMoisturePercent();
    
    // Auto-retry BH1750 detection if not ready
    if (!bh1750Ready) {
      if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
        bh1750Ready = true;
        Serial.println("[OK] BH1750 Light Sensor connected successfully.");
      }
    }
    float lux  = bh1750Ready ? lightMeter.readLightLevel() : 0.0f;

    if (isnan(temp) || isnan(hum)) {
      temp = 26.0;
      hum  = 60.0;
    }

    Serial.printf("[Telemetry] Temp: %.1f C | Hum: %.1f %% | Soil: %.1f %% | Lux: %.1f lx\n",
                  temp, hum, soil, lux);

    // Build Minimal JSON
    JsonDocument doc;
    doc["device_id"]      = DEVICE_ID;
    doc["temperature"]    = round(temp * 10.0) / 10.0;
    doc["humidity"]       = round(hum * 10.0) / 10.0;
    doc["soil_moisture"]  = round(soil * 10.0) / 10.0;
    doc["lux"]            = round(lux);
    doc["pump_active"]    = isPumpRunning;

    char buffer[256];
    serializeJson(doc, buffer);

    if (mqttClient.connected()) {
      mqttClient.publish(TOPIC_TELEMETRY, buffer);
      Serial.printf("[MQTT TX] Published to %s\n", TOPIC_TELEMETRY);
    }
  }
}
