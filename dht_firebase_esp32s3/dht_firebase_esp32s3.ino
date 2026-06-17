#include <WiFi.h>
#include <Firebase_ESP_Client.h>
#include <DHT.h>

// WiFi Credentials
#define WIFI_SSID "BUBT Hub"
#define WIFI_PASSWORD "hub2026"

// Firebase Credentials
#define API_KEY "AIzaSyAKhgwcKqAEIGeQBtWws7ObCUcnqLibhUg"
#define DATABASE_URL "https://bubtvts-f9c65-default-rtdb.asia-southeast1.firebasedatabase.app/"

// DHT Sensor
#define DHTPIN 14
#define DHTTYPE DHT11      // Change to DHT22 if using DHT22

DHT dht(DHTPIN, DHTTYPE);

// Firebase Objects
FirebaseData fbdo;
FirebaseAuth auth;
FirebaseConfig config;

unsigned long lastSend = 0;

void setup() {
  Serial.begin(115200);

  dht.begin();

  // Connect WiFi
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    Serial.print(".");
    delay(500);
  }

  Serial.println();
  Serial.println("WiFi Connected");

  // Firebase Setup
  config.api_key = API_KEY;
  config.database_url = DATABASE_URL;

  if (Firebase.signUp(&config, &auth, "", "")) {
    Serial.println("Firebase Connected");
  } else {
    Serial.printf("Firebase Error: %s\n",
                  config.signer.signupError.message.c_str());
  }

  Firebase.begin(&config, &auth);
  Firebase.reconnectWiFi(true);
}

void loop() {

  if (millis() - lastSend > 500) {
    lastSend = millis();

    float temperature = dht.readTemperature();
    float humidity = dht.readHumidity();

    if (isnan(temperature) || isnan(humidity)) {
      Serial.println("Failed to read DHT sensor!");
      return;
    }

    Serial.print("Temperature: ");
    Serial.print(temperature);
    Serial.print(" °C  ");

    Serial.print("Humidity: ");
    Serial.print(humidity);
    Serial.println(" %");

    // Send to Firebase
    Firebase.RTDB.setFloat(&fbdo, "/DHT/Temperature", temperature);
    Firebase.RTDB.setFloat(&fbdo, "/DHT/Humidity", humidity);
  }
}
