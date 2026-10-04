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
uint32_t lastStatsMs = 0;
uint32_t lastSampleUs = 0;
uint32_t lastLoggedUs = 0;

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

void i2cScan() {
  Serial.println("I2C scan:");
  uint8_t found = 0;
  for (uint8_t address = 1; address < 127; ++address) {
    Wire.beginTransmission(address);
    if (Wire.endTransmission() == 0) {
      Serial.printf("  found device at 0x%02X\n", address);
      ++found;
    }
  }
  if (found == 0) {
    Serial.println("  no I2C devices found (check SDA/SCL/power/AD0)");
  }
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

void setup() {
  Serial.begin(115200);
  delay(1000);
  Serial.println();
  Serial.println("Motion Coach wearable starting");

  Wire.begin(SDA, SCL, 400000);
  i2cScan();

  if (!imu.begin()) {
    Serial.printf("MPU FAILED (WHO_AM_I=0x%02X)\n", imu.whoAmI());
    Serial.println("Check wiring. Not starting BLE.");
    while (true) {
      delay(1000);
    }
  }
  Serial.printf("MPU OK (WHO_AM_I=0x%02X)\n", imu.whoAmI());

  setupBle();
  nextSampleUs = micros();
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
      lastSampleUs = nowUs;
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

  // Diagnostics roughly once per second; never per sample.
  const uint32_t nowMs = millis();
  if (nowMs - lastStatsMs >= 1000) {
    const uint32_t achievedHz = samplesThisSecond;
    samplesThisSecond = 0;
    if (deviceConnected) {
      Serial.printf("Streaming ~%lu Hz | seq=%u | last_dt=%lu us\n",
                    static_cast<unsigned long>(achievedHz), sequence,
                    static_cast<unsigned long>(lastSampleUs - lastLoggedUs));
      lastLoggedUs = lastSampleUs;
    } else {
      Serial.printf("Waiting for client | seq=%u\n", sequence);
    }
    lastStatsMs = nowMs;
  }
}
