#include "mpu6050.h"

namespace motioncoach {

namespace {
inline int16_t combineBigEndian(uint8_t high, uint8_t low) {
  return static_cast<int16_t>((static_cast<uint16_t>(high) << 8) | low);
}
}  // namespace

bool Mpu6050::begin(uint8_t address, int sda_pin, int scl_pin, uint32_t clock_hz) {
  address_ = address;
  Wire.begin(sda_pin, scl_pin, clock_hz);

  if (!writeRegister(MPU6050_REG_PWR_MGMT_1, 0x01)) {
    return false;  // 0x01 wakes the device and selects the X gyro PLL clock
  }
  delay(50);

  // Deterministic ranges chosen to avoid clipping during ordinary arm movement.
  // Keep these in sync with backend/app/sensors/packet.py.
  writeRegister(MPU6050_REG_CONFIG, 0x03);        // DLPF ~44 Hz, 1 kHz gyro rate
  writeRegister(MPU6050_REG_GYRO_CONFIG, 0x10);   // FS_SEL=2 -> +-1000 dps, 32.8 LSB/dps
  writeRegister(MPU6050_REG_ACCEL_CONFIG, 0x08);  // AFS_SEL=1 -> +-4g, 8192 LSB/g
  delay(10);

  // Confirm the device is actually on the bus.
  uint8_t id = whoAmI();
  return id != 0;
}

uint8_t Mpu6050::whoAmI() {
  uint8_t value = 0;
  if (!readRegisters(MPU6050_REG_WHO_AM_I, &value, 1)) {
    return 0;
  }
  return value;
}

bool Mpu6050::readRaw(ImuRaw &out) {
  uint8_t bytes[14] = {0};
  if (!readRegisters(MPU6050_REG_ACCEL_XOUT_H, bytes, sizeof(bytes))) {
    return false;
  }
  out.accel_x = combineBigEndian(bytes[0], bytes[1]);
  out.accel_y = combineBigEndian(bytes[2], bytes[3]);
  out.accel_z = combineBigEndian(bytes[4], bytes[5]);
  out.temperature = combineBigEndian(bytes[6], bytes[7]);
  out.gyro_x = combineBigEndian(bytes[8], bytes[9]);
  out.gyro_y = combineBigEndian(bytes[10], bytes[11]);
  out.gyro_z = combineBigEndian(bytes[12], bytes[13]);
  return true;
}

bool Mpu6050::writeRegister(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(address_);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool Mpu6050::readRegisters(uint8_t start_reg, uint8_t *buffer, size_t length) {
  Wire.beginTransmission(address_);
  Wire.write(start_reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(static_cast<int>(address_), static_cast<int>(length)) !=
      static_cast<int>(length)) {
    return false;
  }
  for (size_t i = 0; i < length; ++i) {
    buffer[i] = static_cast<uint8_t>(Wire.read());
  }
  return true;
}

}  // namespace motioncoach
