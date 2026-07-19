/*
  ============================================================
  ECG Reader - DFRobot/Gravity SEN0213 (AD8232) on ESP32-S3 N16R8
  ============================================================
  Board:   Gravity Analog Heart Rate Monitor Sensor (AD8232)
           https://store.roboticsbd.com/sensors/2326-gravity-analog-heart-rate-monitor-sensor-ecg-for-arduino-robotics-bangladesh.html
  Wiring:  Signal Output -> GPIO 4 (ADC1 channel on ESP32-S3, safe
           to use alongside WiFi/BLE since ADC1 isn't shared with
           the radio like ADC2 is)
           This board variant has no LO+/LO- leads-off pins broken
           out, so we can't detect "electrodes not attached" in
           firmware - a flat/railed signal in the Python monitor
           usually means poor electrode contact.

  Streams raw ECG values over Serial at a STABLE 200 Hz sample
  rate using micros()-based timing instead of delay(). Accurate,
  jitter-free timing matters here because the Python-side
  bandpass/notch filters assume a fixed sample rate (Fs = 200 Hz).
  If sampling jitters, filter behavior degrades and peak/BPM
  detection becomes less reliable.

  Output format (one value per line):
      <raw_adc_value>

  10-bit resolution (0-1023) matches the Python script.

  NOTE: This is a hobbyist/research tool, NOT a certified medical
  device. Do not use it for diagnosis or clinical decisions.
  ============================================================
*/

const int ecgPin = 4;

const unsigned long SAMPLE_INTERVAL_US = 5000UL; // 5 ms -> 200 Hz
unsigned long nextSampleTime = 0;

// The ESP32-S3's ADC has known non-linearity and a few LSBs of noise
// even on a steady input, especially near the rails. Averaging a quick
// burst of reads per output sample smooths that out - this is plain
// hardware oversampling, done cheaply since each analogRead() takes
// roughly 100-200 microseconds (ADC conversion time), well inside our
// 5 ms budget even at 8 reads.
const int OVERSAMPLE_COUNT = 8;

void setup() {
  Serial.begin(115200);

  analogReadResolution(10);        // 0-1023 range, matches Python side
  analogSetAttenuation(ADC_11db);  // full ~0-3.3V input range, needed
                                    // since AD8232 output rides on
                                    // ~1.65V bias and can swing close
                                    // to both rails

  nextSampleTime = micros();
}

void loop() {
  unsigned long now = micros();

  if (now >= nextSampleTime) {
    long sum = 0;
    for (int i = 0; i < OVERSAMPLE_COUNT; i++) {
      sum += analogRead(ecgPin);
    }
    int ecgValue = sum / OVERSAMPLE_COUNT;
    Serial.println(ecgValue);

    nextSampleTime += SAMPLE_INTERVAL_US;

    // If we ever fall behind (e.g. Serial buffer stalls), resync
    // instead of trying to "catch up" with a burst of samples,
    // which would otherwise distort the timing the filters rely on.
    if ((long)(now - nextSampleTime) > 0) {
      nextSampleTime = now + SAMPLE_INTERVAL_US;
    }
  }
}