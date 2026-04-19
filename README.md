# STS3215

MicroPython driver and demo code for Feetech **STS3215** serial bus servos,
targeted at the Raspberry Pi Pico (RP2040).

Companion code for the YouTube video
*"Bus Servos are SO Much Better — Here's Why (STS3215 + Pico)"*.

## Files

| File | Purpose |
| --- | --- |
| `sts3215.py` | The driver library. Copy this to the Pico filesystem — every other script imports from it. |
| `setup_id.py` | One-shot utility for changing a servo's bus ID. STS3215s ship with ID `1`, so connect **one servo at a time** and run this to assign unique IDs before daisy-chaining. |
| `demo.py` | The mini demo featured in the video. Two servos (IDs 1 and 2) daisy-chained on a single bus sweep in a wave pattern, with live position feedback printed to the terminal. |
| `demo02.py` | A simpler single-servo example. Moves servo ID 1 between its minimum and maximum positions and polls position/speed/moving state until each move completes — useful for sanity-checking a new setup. |

## Wiring

The scripts default to UART0 with `TX = GP0`, `RX = GP1`, at 1 Mbaud — which
matches the Waveshare Serial Bus Servo Driver Board for the Pico. Power the
servos from a 7.4 V supply (a 2S LiPo works well).

## Deploying

Copy `sts3215.py` (plus whichever script you want to run) to the Pico:

```
mpremote cp sts3215.py :
mpremote cp demo.py :
mpremote run demo.py
```

Thonny works too — just open the files and save them to the device.

## Requirements

- MicroPython firmware on an RP2040 (or any MicroPython board with a free UART)
- No CPython dependencies — the driver uses only `machine` and `time`
