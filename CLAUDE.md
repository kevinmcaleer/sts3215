# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MicroPython driver for **Feetech STS3215 serial bus servos**. The entire codebase is a single module (`sts3215.py`) intended to run on MicroPython-capable microcontrollers (e.g., RP2040/Pico).

## Architecture

- `STS3215` class: communicates with servos over UART using the Feetech serial protocol (0xFF 0xFF header, checksum-terminated packets)
- Supports an optional direction pin for half-duplex UART via tri-state buffer
- Position range: 0-4095 maps to 0-360 degrees
- Standalone helper functions `degrees_to_position()` / `position_to_degrees()` for unit conversion

## Key Constraints

- **MicroPython only** — uses `machine.UART`, `machine.Pin`, and `time` from the MicroPython stdlib. Do not use CPython-only modules.
- All timing uses `time.sleep_ms()` / `time.sleep_us()` (MicroPython API, not `time.sleep()`).
- No build system, no tests, no dependencies beyond MicroPython firmware.

## Deploying

Copy `sts3215.py` to the microcontroller filesystem (e.g., via `mpremote cp sts3215.py :` or Thonny).

## Testing

for each new feature, bugfix or change run the suite of tests in tests/ to verify that the code is working as expected. Tests can be run using pytest or any other testing framework that supports MicroPython.
for each new feature - be sure to create new tests to ensure the code works as expected and to prevent regressions in the future. Tests should cover a variety of scenarios, including edge cases and error handling.
code coverage should be 80% or higher.