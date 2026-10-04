# Motion Coach Wearable Firmware (XIAO ESP32-C5)

Single-MCU wearable: the ESP32-C5 reads the MPU6050 directly over I2C and streams
packets to the Mac over BLE. The STM32 is **not** in this path.

```
MPU6050 --I2C--> XIAO ESP32-C5 --BLE notify--> Mac / Python (bleak)
```

## Provenance

- PlatformIO configuration is copied from the known-good reference project
  [`kovac04/auto-lock`](https://github.com/kovac04/auto-lock)
  (`esp32/lock_receiver/platformio.ini`).
- BLE server / advertising / reconnect boilerplate is adapted from
  `auto-lock/esp32/lock_receiver/src/main.cpp`; servo, lock state, and TOGGLE
  logic were removed.
- MPU6050 register behavior (`0x68`, wake `0x6B=0x01`, 14-byte burst at `0x3B`,
  big-endian signed decode) is reimplemented from `auto-lock/Core/Src/main.c`.
- Nothing was copied from the reference repo's history; files were copied and
  adapted in this repository.

## Wiring (verified against the board variant)

Pins confirmed from the installed `XIAO_ESP32C5` Arduino variant
(`SDA = GPIO23`, `SCL = GPIO24`), **not** guessed.

| MPU6050 breakout | XIAO ESP32-C5 | Notes |
| --- | --- | --- |
| VCC | `3V3` | MPU6050 is a 3.3 V part; most GY-521 breakouts also accept 5 V, but use 3V3 here |
| GND | `GND` | common ground |
| SDA | `D4` (GPIO23) | I2C data |
| SCL | `D5` (GPIO24) | I2C clock |
| AD0 | `GND` | selects address `0x68` |
| INT | *unused* | not needed |

- Power the board over USB-C; use jumper wires for bring-up.
- Most MPU6050 breakout boards include pull-ups and a 3.3 V regulator. If you have
  a bare MPU6050 chip (no breakout), do not connect more than 3.3 V.
- **Do not solder** the boards together until I2C and BLE streaming both work.

## Build and upload

Requires PlatformIO (`pio`). From the repo root:

```sh
make firmware-build      # compile only
make firmware-upload     # compile + flash over USB-C
make firmware-monitor    # 115200-baud serial monitor
```

Equivalent:

```sh
cd firmware/esp32-wearable
pio run
pio run --target upload
pio device monitor
```

If upload does not start, hold **BOOT**, briefly press **RESET**, release **BOOT**,
and retry.

### Known toolchain fix (needed on a fresh PlatformIO install)

PlatformIO Core may install its default `tool-esptoolpy` (esptool 4.11) even though
the Seeed platform needs esptool 5.x. That produces:

```
esptool: error: unrecognized arguments: --flash-mode --flash-freq ...
```

Fix by removing the stale package so the Seeed platform installs its own v5.1.2:

```sh
mv ~/.platformio/packages/tool-esptoolpy /tmp/tool-esptoolpy.bak 2>/dev/null || true
cd firmware/esp32-wearable && pio run
```

## Bring-up test procedure

### STAGE 2 — I2C / sensor only (USB serial)

1. Wire per the table, connect USB-C, run `make firmware-upload`, then `make firmware-monitor`.
2. Expect on boot:
   ```
   I2C scan:
     found device at 0x68
   MPU OK (WHO_AM_I=0x68)
   BLE advertising as MotionCoach-IMU
   Waiting for client | seq=0
   ```
3. **Stationary:** over ~1 s, one accelerometer axis should sit near ±16000
   (~1 g = 16384 LSB) depending on orientation; the other two near 0; gyro near 0.
4. **Move the sensor:** the six raw values should clearly change.
5. If `WHO_AM_I` is not `0x68` or no device is found, see debugging below.

### STAGE 3 — BLE streaming (Mac)

1. Keep the wearable powered and advertising.
2. On the Mac: `make imu-monitor`
3. Expect a connected address and roughly `~50 Hz` with `gaps=0`.

## Debugging direct I2C

Run the firmware and read the serial output:

- `no I2C devices found` → check SDA=D4 / SCL=D5, 3V3, GND, and AD0=GND.
- Found a device but not `0x68` → AD0 may be high (`0x69`).
- `MPU FAILED` → wiring or power; confirm the breakout LED (if any) and 3.3 V.
- Intermittent reads → shorter jumpers, ensure common ground; try lower I2C clock
  (change `Wire.begin(SDA, SCL, 400000)` to `100000`).

Fallback if direct ESP32→MPU6050 stays unreliable: the already-proven
`MPU6050 → STM32 → UART → ESP32 → BLE` path has working code in `auto-lock`.

## BLE protocol

- Device name: `MotionCoach-IMU`
- Service: `8a1f0001-6b2e-4c3d-9e5f-0a1b2c3d4e5f`
- IMU data characteristic (NOTIFY): `8a1f0002-6b2e-4c3d-9e5f-0a1b2c3d4e5f`
- Control characteristic (WRITE / WRITE_NR): `8a1f0003-6b2e-4c3d-9e5f-0a1b2c3d4e5f`
  - accepts `START`, `STOP`, `PING`

Notification payload, exactly 18 bytes, little-endian (matches Python
`struct.unpack("<HIhhhhhh", data)`):

| offset | type | field |
| --- | --- | --- |
| 0 | uint16 | sequence |
| 2 | uint32 | timestamp_ms (device `millis()`) |
| 6 | int16 | ax |
| 8 | int16 | ay |
| 10 | int16 | az |
| 12 | int16 | gx |
| 14 | int16 | gy |
| 16 | int16 | gz |

15–16 bytes of standard BLE notification payload were available; 18 bytes fits
within the default ATT MTU (23). If a future MTU negotiation changes, recheck.

## Sampling

- 50 Hz target (`SAMPLE_PERIOD_US = 20000`), scheduled with `micros()`.
- Raw integers are streamed; scaling happens on the Mac.
- Serial diagnostics print about once per second, never per sample.
