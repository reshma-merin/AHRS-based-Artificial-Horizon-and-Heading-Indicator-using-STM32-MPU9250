# AHRS-based-Artificial-Horizon-and-Heading-Indicator-using-STM32-MPU9250


A low-cost Attitude and Heading Reference System (AHRS) built on the **STM32L432KC** and **MPU9250** nine-axis IMU, simulating two classic cockpit flight instruments — an artificial horizon and a heading indicator — in real time.

🎥 **Demo video:** (https://www.youtube.com/watch?v=gq29Ls3hVIY&t=49s)

---

## Overview

This project implements a complete embedded sensor-fusion pipeline: an STM32L432KC polls an MPU9250 over I2C, runs a gradient-descent quaternion fusion filter (Madgwick/Mahony-style) to combine accelerometer, gyroscope, and magnetometer data, and streams the resulting orientation over UART to a PC. A custom PyGame application then renders that data as a live, aviation-style artificial horizon and heading indicator.

## Hardware

| Component | Details |
|---|---|
| Microcontroller | STM32L432KC Nucleo-32 (ARM Cortex-M4) |
| IMU | MPU9250 breakout board (accelerometer, gyroscope, AK8963 magnetometer) |
| Wiring | 4 jumper wires — 3V3, GND, SCL (PB6), SDA (PB7); no external components |
| Connection | USB (powers the board and carries UART data via the onboard ST-Link virtual COM port) |
<img width="752" height="319" alt="image" src="https://github.com/user-attachments/assets/d6c77d8d-55d4-4ff3-a020-a71864b128c7" />


## How It Works

1. **I2C1** (Fast Mode, 400 kHz) reads raw accelerometer, gyroscope, and magnetometer data from the MPU9250.
2. **TIM1** provides microsecond-precision timing used internally by the fusion filter.
3. On boot, the firmware runs self-tests, gyro/accelerometer bias calibration, and magnetometer hard-iron/soft-iron calibration (a figure-eight motion is required for this step).
4. Raw sensor counts are scaled to physical units and fused into a quaternion using a gradient-descent filter, then converted to yaw, pitch, and roll.
5. **USART2** (115200 baud) streams the orientation data over the ST-Link virtual COM port to a host PC.
6. A PyGame application reads the serial stream and renders a live artificial horizon and heading indicator.

## Repository Contents

- `Core/` — STM32CubeIDE firmware source (main application logic, HAL configuration)
- `mpu9255.c` / `mpu9255.h` / `mpu9255_defs.h` — Ported and adapted MPU9250/AK8963 driver and quaternion fusion library
- `simulation.py` — PyGame visualization client (artificial horizon + heading indicator)
- `Project-AHRS-I.ioc` — STM32CubeMX project configuration

## Getting Started

**Firmware:**
1. Open the project in STM32CubeIDE.
2. Wire the MPU9250 to the Nucleo-32 as described above.
3. Build and flash using **Run** (not Debug).

**Visualization:**
```bash
pip install pygame pyserial
python simulation.py
```
Edit the `PORT_NAME` variable in `simulation.py` to match your board's COM port before running.

## Results
<img width="596" height="372" alt="image" src="https://github.com/user-attachments/assets/a1d3bf0b-694c-4105-96bc-81f82ec89cef" />

- Full sensor pipeline (I2C communication, calibration, quaternion fusion, UART streaming) verified end-to-end.
- Orientation stabilizes within ~10–15 seconds of boot and holds under 0.1° of drift over several minutes of continuous operation.
- All test cases from the original project proposal — I2C device detection, raw sensor validation, magnetometer calibration, gyro drift, compass heading accuracy, and extended serial reliability — were completed successfully.
- Diagnosed and resolved a magnetic interference issue where nearby electronics (laptop/USB) distorted magnetometer readings and destabilized the fusion output.

## Acknowledgments

Built on top of the quaternion AHRS library and approach originally developed by [Ibrahim Cahit Özdemir](https://github.com/ibrahimcahit/MPU9255-Quaternion-AHRS-STM32), adapted here for the STM32L432KC.

## Author

Reshma Merin Thomas 
