// Motion Coach wearable firmware — XIAO ESP32-C5 as a BLE IMU peripheral.
//
// Architecture:
//   MPU6050 --I2C--> XIAO ESP32-C5 --BLE notify--> Mac/Python (bleak)
//
// Provenance: the BLE server / advertising / reconnect boilerplate is adapted
// from the known-good receiver in auto-lock:
//   https://github.com/kovac04/auto-lock  (esp32/lock_receiver/src/main.cpp)
// Servo, lock-state, and TOGGLE logic have been removed. The MPU6050 burst
// decode follows auto-lock's STM32 implementation.
//
// Boxed packet (18 bytes, little-endian):
//   uint16 sequence | uint32 timestamp_ms | int16 ax, ay, az, gx, gy, gz

#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <Wire.h>

#include "mpu6050.h"

// --- Motion Coach BLE identities (new; not the lock UUIDs) -----------------
#define MOTION_SERVICE_UUID "8a1f0001-6b2e-4c3d-9e5f-0a1b2c3d4e5f"
#define IMU_DATA_CHARACTERISTIC_UUID "8a1f0002-6b2e-4c3d-9e5f-0a1b2c3d4e5f"
#define CONTROL_CHARACTERISTIC_UUID "8a1f0003-6b2e-4c3d-9e5f-0a1b2c3d4e5f"

constexpr char DEVICE_NAME[] = "MotionCoach-IMU";

// --- Sampling --------------------------------------------------------------
constexpr uint32_t SAMPLE_RATE_HZ = 50;
constexpr uint32_t SAMPLE_PERIOD_US = 1000000UL / SAMPLE_RATE_HZ;  // 20000 us
constexpr size_t IMU_PACKET_SIZE = 18;

motioncoach::Mpu6050 imu;

BLEServer* bleServer = nullptr;
BLECharacteristic* imuCharacteristic = nullptr;
volatile bool deviceConnected = false;
volatile bool streamingEnabled = true;

uint16_t sequence = 0;
uint32_t nextSampleUs = 0;
uint32_t samplesThisSecond = 0;
uint32_t totalSamples = 0;
uint32_t lastStatsMs = 0;
uint8_t mpuAddress = 0;
motioncoach::ImuRaw lastRaw = {};
bool haveRaw = false;

// Pack fields explicitly little-endian so we never depend on compiler padding.
void packPacket(uint8_t* out, uint16_t seq, uint32_t timestamp_ms,
                const motioncoach::ImuRaw& raw) {
  out[0] = static_cast<uint8_t>(seq & 0xFF);
  out[1] = static_cast<uint8_t>((seq >> 8) & 0xFF);
  out[2] = static_cast<uint8_t>(timestamp_ms & 0xFF);
  out[3] = static_cast<uint8_t>((timestamp_ms >> 8) & 0xFF);
  out[4] = static_cast<uint8_t>((timestamp_ms >> 16) & 0xFF);
  out[5] = static_cast<uint8_t>((timestamp_ms >> 24) & 0xFF);

  const int16_t values[6] = {raw.accel_x, raw.accel_y, raw.accel_z,
                             raw.gyro_x,  raw.gyro_y,  raw.gyro_z};
  for (size_t i = 0; i < 6; ++i) {
    const uint16_t bits = static_cast<uint16_t>(values[i]);
    out[6 + i * 2] = static_cast<uint8_t>(bits & 0xFF);
    out[7 + i * 2] = static_cast<uint8_t>((bits >> 8) & 0xFF);
  }
}

// Scans the currently configured Wire bus. Prints every address when verbose.
// Returns 0x68 or 0x69 if an MPU6050-compatible device responds, else 0.
// AD0 may be unconnected; the address is discovered, never assumed.
uint8_t scanAddresses(bool verbose) {
  uint8_t count = 0;
  bool saw68 = false;
  bool saw69 = false;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      if (verbose) {
        Serial.printf("Found 0x%02X\n", address);
      }
      ++count;
      if (address == 0x68) saw68 = true;
      if (address == 0x69) saw69 = true;
    }
  }
  if (count == 0 && verbose) {
    Serial.println("(no devices)");
  }
  if (saw68) return 0x68;  // prefer 0x68 if both respond
  if (saw69) return 0x69;
  return 0;
}

// Try the documented pins and speed first; if nothing answers, try a lower
// speed and the swapped pin order. This distinguishes software/config problems
// from a dead or unpowered sensor without guessing.
uint8_t discoverMpu(int& sda, int& scl, uint32_t& clock_hz) {
  Wire.end();
  Wire.begin(sda, scl, clock_hz);
  delay(20);
  Serial.println("I2C scan...");
  uint8_t addr = scanAddresses(true);
  if (addr != 0) {
    return addr;
  }

  struct Config {
    int sda;
    int scl;
    uint32_t hz;
  };
  const Config alternates[] = {
      {sda, scl, 100000},   // lower speed
      {scl, sda, 400000},   // swapped pins
      {scl, sda, 100000},   // swapped + lower speed
  };
  Serial.println("Retrying I2C with alternate configurations...");
  for (const Config& config : alternates) {
    Wire.end();
    Wire.begin(config.sda, config.scl, config.hz);
    delay(20);
    Serial.printf("SDA=%d SCL=%d @%lukHz: ", config.sda, config.scl,
                  static_cast<unsigned long>(config.hz / 1000));
    const uint8_t found = scanAddresses(false);
    if (found != 0) {
      Serial.printf("found 0x%02X (using this configuration)\n", found);
      sda = config.sda;
      scl = config.scl;
      clock_hz = config.hz;
      return found;
    }
    Serial.println("none");
  }
  return 0;
}

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer*) override {
    deviceConnected = true;
    Serial.println("BLE connected");
  }

  void onDisconnect(BLEServer* server) override {
    deviceConnected = false;
    Serial.println("BLE disconnected");
    server->startAdvertising();
    Serial.println("Advertising restarted");
  }
};

class ControlCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic* characteristic) override {
    String command = characteristic->getValue();
    command.trim();
    command.toUpperCase();
    if (command == "START") {
      streamingEnabled = true;
      Serial.println("Control: START");
    } else if (command == "STOP") {
      streamingEnabled = false;
      Serial.println("Control: STOP");
    } else if (command == "PING") {
      Serial.println("Control: PING");
    }
  }
};

void setupBle() {
  BLEDevice::init(DEVICE_NAME);
  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());

  BLEService* service = bleServer->createService(MOTION_SERVICE_UUID);

  // Notify-only. The BLE stack auto-adds the 0x2902 client-configuration
  // descriptor; adding one manually is deprecated in arduino-esp32 3.x.
  imuCharacteristic =
      service->createCharacteristic(IMU_DATA_CHARACTERISTIC_UUID,
                                    BLECharacteristic::PROPERTY_NOTIFY);

  BLECharacteristic* control = service->createCharacteristic(
      CONTROL_CHARACTERISTIC_UUID,
      BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  control->setCallbacks(new ControlCallbacks());

  service->start();

  BLEAdvertising* advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(MOTION_SERVICE_UUID);
  advertising->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BLE advertising as MotionCoach-IMU");
}

void haltForever() {
  while (true) {
    delay(1000);
  }
}

// WHO_AM_I values from the MPU6xxx/9xxx family. These share the register map and
// the 0x3B 14-byte burst we use, so all are acceptable:
//   0x68 MPU6050, 0x70 MPU6500, 0x71 MPU9250, 0x73 MPU9255, 0x98 common clone
bool isCompatibleWhoAmI(uint8_t who) {
  return who == 0x68 || who == 0x70 || who == 0x71 || who == 0x73 || who == 0x98;
}

// Characterizes the two I2C lines so a wiring fault can be told apart from a
// dead/unpowered sensor: idle level, external pull-up presence, the ESP32's
// ability to drive each line, and whether SDA/SCL are shorted together.
void reportLineLevels(int sda, int scl) {
  pinMode(sda, INPUT);
  pinMode(scl, INPUT_PULLUP);
  delay(3);
  const int sdaExt = digitalRead(sda);

  pinMode(scl, INPUT);
  pinMode(sda, INPUT_PULLUP);
  delay(3);
  const int sclExt = digitalRead(scl);

  // Drive each line and read it back (rules out a damaged/shorted pin).
  pinMode(sda, OUTPUT);
  digitalWrite(sda, LOW);
  delay(2);
  const int sdaLow = digitalRead(sda);
  digitalWrite(sda, HIGH);
  delay(2);
  const int sdaHigh = digitalRead(sda);

  pinMode(sda, INPUT_PULLUP);
  pinMode(scl, OUTPUT);
  digitalWrite(scl, LOW);
  delay(2);
  const int sclLow = digitalRead(scl);
  digitalWrite(scl, HIGH);
  delay(2);
  const int sclHigh = digitalRead(scl);

  // Cross test: while one line is driven low, does the other follow?
  pinMode(scl, INPUT_PULLUP);
  pinMode(sda, OUTPUT);
  digitalWrite(sda, LOW);
  delay(2);
  const int sclWithSdaLow = digitalRead(scl);
  pinMode(sda, INPUT_PULLUP);
  pinMode(scl, OUTPUT);
  digitalWrite(scl, LOW);
  delay(2);
  const int sdaWithSclLow = digitalRead(sda);

  // Decisive test: with internal pull-downs on, a strong external pull-up wins.
  pinMode(sda, INPUT_PULLDOWN);
  pinMode(scl, INPUT_PULLDOWN);
  delay(5);
  const int sdaPd = digitalRead(sda);
  const int sclPd = digitalRead(scl);

  pinMode(sda, INPUT);
  pinMode(scl, INPUT);

  Serial.printf("Line idle (no internal PU): SDA=%d SCL=%d\n", sdaExt, sclExt);
  Serial.printf("External pull-up test (internal pull-down on): SDA=%d SCL=%d\n", sdaPd, sclPd);
  if (sdaPd == 1 && sclPd == 1) {
    Serial.println("  -> external pull-ups present (breakout likely powered)");
  } else {
    Serial.println("  -> NO strong external pull-ups (breakout may be unpowered)");
  }
  Serial.printf("Drive test SDA low/high=%d/%d SCL low/high=%d/%d\n", sdaLow, sdaHigh,
                sclLow, sclHigh);
  Serial.printf("Cross test: SCL while SDA low=%d, SDA while SCL low=%d\n", sclWithSdaLow,
                sdaWithSclLow);
  if (sclWithSdaLow == 0 || sdaWithSclLow == 0) {
    Serial.println("  WARNING: SDA and SCL appear shorted together.");
  }
  if (sdaLow != 0 || sdaHigh != 1 || sclLow != 0 || sclHigh != 1) {
    Serial.println("  WARNING: a pin cannot be driven correctly (damaged/shorted).");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("MotionCoach wearable starting");
  Serial.printf("SDA=%d SCL=%d\n", SDA, SCL);
  reportLineLevels(SDA, SCL);

  int sda = SDA;
  int scl = SCL;
  uint32_t clockHz = 400000;
  const uint8_t detected = discoverMpu(sda, scl, clockHz);
  if (detected == 0) {
    Serial.println("ERROR: no I2C device found");
    Serial.println("Check 3V3, GND, SDA=D4/GPIO23, SCL=D5/GPIO24, and that the");
    Serial.println("breakout is powered (some clones need 5V on VCC).");
    haltForever();
  }
  mpuAddress = detected;
  Serial.printf("Using SDA=%d SCL=%d @%lukHz addr=0x%02X\n", sda, scl,
                static_cast<unsigned long>(clockHz / 1000), mpuAddress);

  if (!imu.begin(mpuAddress, sda, scl, clockHz)) {
    Serial.printf("ERROR: MPU did not respond at 0x%02X\n", mpuAddress);
    haltForever();
  }

  const uint8_t who = imu.whoAmI();
  Serial.printf("MPU WHO_AM_I=0x%02X\n", who);
  if (!isCompatibleWhoAmI(who)) {
    Serial.printf("ERROR: unexpected WHO_AM_I=0x%02X at 0x%02X\n", who, mpuAddress);
    Serial.println("Refusing to stream until the sensor identity is confirmed.");
    haltForever();
  }
  if (who != 0x68) {
    Serial.println("  (MPU6500-class part; register-compatible with MPU6050 for this burst)");
  }
  Serial.println("MPU initialized");

  setupBle();
  nextSampleUs = micros();
  lastStatsMs = millis();
}

void loop() {
  const uint32_t nowUs = micros();

  if (static_cast<int32_t>(nowUs - nextSampleUs) >= 0) {
    nextSampleUs += SAMPLE_PERIOD_US;
    // If we fell far behind, resync instead of bursting to catch up.
    if (static_cast<int32_t>(nowUs - nextSampleUs) > static_cast<int32_t>(SAMPLE_PERIOD_US * 5)) {
      nextSampleUs = nowUs;
    }

    motioncoach::ImuRaw raw;
    if (imu.readRaw(raw)) {
      lastRaw = raw;
      haveRaw = true;
      ++totalSamples;
      if (deviceConnected && streamingEnabled) {
        uint8_t packet[IMU_PACKET_SIZE];
        packPacket(packet, sequence, millis(), raw);
        imuCharacteristic->setValue(packet, IMU_PACKET_SIZE);
        imuCharacteristic->notify();
        ++sequence;
      }
      ++samplesThisSecond;
    }
  }

  // Diagnostics ~once per second, whether or not a BLE client is connected, so
  // the sensor can be validated over USB serial before BLE is trusted.
  const uint32_t nowMs = millis();
  if (nowMs - lastStatsMs >= 1000) {
    const uint32_t elapsedMs = nowMs - lastStatsMs;
    const float rateHz = elapsedMs ? (samplesThisSecond * 1000.0f / elapsedMs) : 0.0f;
    samplesThisSecond = 0;
    lastStatsMs = nowMs;
    if (haveRaw) {
      Serial.printf(
          "addr=0x%02X ax=%d ay=%d az=%d gx=%d gy=%d gz=%d total=%lu rate=%.1fHz ble=%s\n",
          mpuAddress, lastRaw.accel_x, lastRaw.accel_y, lastRaw.accel_z,
          lastRaw.gyro_x, lastRaw.gyro_y, lastRaw.gyro_z,
          static_cast<unsigned long>(totalSamples), rateHz,
          deviceConnected ? "connected" : "advertising");
    } else {
      Serial.println("addr=0x?? no sensor samples yet");
    }
  }
}
