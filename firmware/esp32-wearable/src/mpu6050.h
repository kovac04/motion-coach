// MPU6050 direct I2C driver for the XIAO ESP32-C5 wearable.
//
// Register behavior and the 14-byte burst decode are reimplemented from the
// known-good STM32 implementation in auto-lock:
//   https://github.com/kovac04/auto-lock  (Core/Src/main.c)
// That reference proved address 0x68, wake via PWR_MGMT_1 (0x6B), and a 14-byte
// read starting at 0x3B with big-endian signed 16-bit fields.
//
// Written with Arduino Wire so the STM32 is not in the runtime path.

#pragma once

#include <Arduino.h>
#include <Wire.h>

namespace motioncoach {

constexpr uint8_t MPU6050_DEFAULT_ADDRESS = 0x68;  // AD0 low

// MPU6050 register map (subset).
constexpr uint8_t MPU6050_REG_CONFIG = 0x1A;
constexpr uint8_t MPU6050_REG_GYRO_CONFIG = 0x1B;
constexpr uint8_t MPU6050_REG_ACCEL_CONFIG = 0x1C;
constexpr uint8_t MPU6050_REG_ACCEL_XOUT_H = 0x3B;
constexpr uint8_t MPU6050_REG_PWR_MGMT_1 = 0x6B;
constexpr uint8_t MPU6050_REG_WHO_AM_I = 0x75;

// Raw signed 16-bit readings straight from the sensor. No float conversion on
// the MCU; the Python side scales later.
struct ImuRaw {
  int16_t accel_x;
  int16_t accel_y;
  int16_t accel_z;
  int16_t temperature;
  int16_t gyro_x;
  int16_t gyro_y;
  int16_t gyro_z;
};

class Mpu6050 {
 public:
  // Initializes Wire on the given pins and wakes the sensor. Returns false if
  // the device does not respond at `address`.
  bool begin(uint8_t address = MPU6050_DEFAULT_ADDRESS,
             int sda_pin = SDA,
             int scl_pin = SCL,
             uint32_t clock_hz = 400000);

  // Reads WHO_AM_I (0x75). Returns 0 if the read failed.
  uint8_t whoAmI();

  // Reads the 14-byte burst beginning at ACCEL_XOUT_H (0x3B).
  bool readRaw(ImuRaw &out);

  uint8_t address() const { return address_; }

 private:
  bool writeRegister(uint8_t reg, uint8_t value);
  bool readRegisters(uint8_t start_reg, uint8_t *buffer, size_t length);

  uint8_t address_ = MPU6050_DEFAULT_ADDRESS;
};

}  // namespace motioncoach
