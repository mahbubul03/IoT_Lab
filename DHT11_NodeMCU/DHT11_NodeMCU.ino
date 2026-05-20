#include <DHT.h>

#define DHTPIN D4
#define DHTTYPE DHT11

DHT dht(DHTPIN, DHTTYPE);

void setup() {
  Serial.begin(115200);
  dht.begin();
  Serial.println("DHT11 Ready!");
}

void loop() {
  delay(10000); // 10 second delay

  float humidity = dht.readHumidity();
  float tempC    = dht.readTemperature();

  if (isnan(humidity) || isnan(tempC)) {
    Serial.println("Sensor error! Check wiring.");
    return;
  }

  Serial.print("Temp     : "); Serial.print(tempC); Serial.println(" C");
  Serial.print("Humidity : "); Serial.print(humidity); Serial.println(" %");
  Serial.println("--------------------------");
}