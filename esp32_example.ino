#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// --- Configuration ---
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// Replace this with the local IP address of the computer running your FastAPI backend
// e.g., "192.168.1.100" (You can find this by running 'ipconfig' in your command prompt)
const char* serverUrl = "http://10.186.47.62:8000/api/sensors/telemetry";

// Interval between telemetry pushes (in milliseconds)
const unsigned long timerDelay = 5000; 
unsigned long lastTime = 0;

void setup() {
  Serial.begin(115200);

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  Serial.println("Connecting to Wi-Fi...");
  while(WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  
  Serial.println("");
  Serial.print("Connected to WiFi network with IP Address: ");
  Serial.println(WiFi.localIP());
}

void loop() {
  // Send an HTTP POST request every 5 seconds
  if ((millis() - lastTime) > timerDelay) {
    
    // Check WiFi connection status
    if(WiFi.status() == WL_CONNECTED) {
      HTTPClient http;
      
      // Specify the destination URL
      http.begin(serverUrl);
      
      // Specify content-type header
      http.addHeader("Content-Type", "application/json");

      // 1. Gather Sensor Data 
      // (Replace these simulated values with your real DHT22, Soil Moisture, and BH1750 Lux sensor readings!)
      float currentTemperature = 26.5;
      float currentHumidity = 62.0;
      int currentMoisture = 45;
      int currentLux = 12500;

      // 2. Build the JSON Payload
      // Using ArduinoJson library (Install it via Arduino Library Manager)
      StaticJsonDocument<200> doc;
      doc["temperature"] = currentTemperature;
      doc["humidity"] = currentHumidity;
      doc["moisture_percent"] = currentMoisture;
      doc["lux"] = currentLux;

      String requestBody;
      serializeJson(doc, requestBody);
      
      Serial.print("Sending Payload: ");
      Serial.println(requestBody);

      // 3. Send the HTTP POST request
      int httpResponseCode = http.POST(requestBody);
      
      // 4. Handle the Response
      if (httpResponseCode > 0) {
        Serial.print("HTTP Response code: ");
        Serial.println(httpResponseCode);
        String payload = http.getString();
        Serial.println("Server Response: " + payload);
      } else {
        Serial.print("Error code: ");
        Serial.println(httpResponseCode);
      }
      
      // Free resources
      http.end();
    } else {
      Serial.println("WiFi Disconnected");
    }
    
    lastTime = millis();
  }
}
