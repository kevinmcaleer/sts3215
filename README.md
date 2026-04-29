# Buddy

A MicroPython-powered 6-DOF robot arm built around Feetech **STS3215** serial
bus servos. Targets RP2040 (Raspberry Pi Pico W or equivalent) and ships with
a small web UI — sliders, 3D viewer, IK target controls, and a command
console — served from the device itself over Wi-Fi.

> See [`design/epic.md`](design/epic.md) for the project's vision and
> [`docs/api.md`](docs/api.md) for the HTTP/JSON API reference.

## Hardware

| Item | Notes |
| --- | --- |
| Microcontroller | RP2040 with Wi-Fi (Pico W). Any MicroPython board with a free UART works for the servo bus, but the web UI needs the Wi-Fi-capable variant. |
| 6 × Feetech STS3215 servos | Daisy-chained on a single half-duplex bus. |
| Servo driver board | e.g. Waveshare *Serial Bus Servo Driver Board for Pico* — exposes the half-duplex tri-state buffer the protocol needs. |
| Power | 7.4 V (2S LiPo) for the servos. The Pico runs from USB or a regulated 5 V rail; **do not** power the servo bus from the Pico. |
| Wiring | UART0 with `TX = GP0`, `RX = GP1`, 1 Mbaud (the Waveshare board's default). |

## First-time setup

### 1. Flash MicroPython

Download the latest MicroPython firmware for your board (Pico W:
`RPI_PICO_W-*.uf2`), hold BOOTSEL, plug in USB, and copy the .uf2 file onto
the mounted volume. The board reboots into MicroPython.

### 2. Assign servo IDs

STS3215s ship with ID `1`. Connect **one servo at a time** to the bus and run
`setup_id.py` to give each a unique ID (1–6 by convention: base, shoulder,
elbow, wrist_pitch, wrist_roll, gripper).

```
mpremote cp sts3215.py :
mpremote cp setup_id.py :
mpremote run setup_id.py   # edit the script to set the new ID before running
```

Once each servo has a unique ID, daisy-chain them together.

### 3. Copy the project to the device

```
mpremote cp sts3215.py :
mpremote cp buddy.py :
mpremote cp config.py :
mpremote cp kinematics.py :
mpremote cp wifi.py :
mpremote cp server.py :
mpremote cp -r www :
```

(Thonny works too — just open and save each file. Skip the demo / test
files; they aren't needed at runtime.)

### 4. Calibrate joint offsets

With torque off, hold the arm in its **home pose** (all joints at 0° in your
chosen convention — typically arm extended straight up) and run:

```
mpremote run calibrate.py
```

This reads each servo's raw position and writes a `config.json` to the
device flash with `offset_deg` per joint, so subsequent reads/writes use a
clean user frame (0° = home).

### 5. Wi-Fi provisioning

On first boot the device finds no Wi-Fi credentials and starts an open
access point named **`Buddy-Setup`** (configurable). Join it from your phone
or laptop, browse to the device IP printed on USB serial — typically
`http://192.168.4.1` — and POST your home-network credentials:

```
curl -X POST http://192.168.4.1/api/wifi \
  -H 'Content-Type: application/json' \
  -d '{"ssid": "yourwifi", "password": "yourpassword"}'
```

Reboot the device. It now joins your home network and prints its new IP on
USB serial. Visit that IP in a browser to use the UI.

## Boot script

A minimal `main.py` (which MicroPython runs automatically on boot) ties it
all together:

```python
from sts3215 import STS3215
from buddy import Buddy
from wifi import boot_network
from server import Server

bus    = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy  = Buddy(bus, config_path="/config.json")
net    = boot_network()
print("network:", net)

# STS3215 encoders are absolute, so `read_all_positions()` is already correct
# on first boot. Park the arm at a known reference pose anyway:
buddy.set_torque_all(True)
buddy.home(duration_ms=1500)

Server(buddy).serve_forever(host="0.0.0.0", port=80)
```

## Web UI

Open the device's IP in a browser. The UI is served from the device's
`/www/` directory and includes:

- **3D viewer** (Three.js, loaded from a CDN) — live model of the arm.
- **Joints** — slider per joint, debounced live control; torque on/off.
- **Gripper** — open / close.
- **Pose target** — XYZ + orientation entry. **Preview** runs IK without
  moving so you can sanity-check the joint angles; **Go** commits the move.
- **Console** — text command panel with grammar
  `move`, `pose`, `torque`, `gripper`, `status`, `home`. Up/Down recalls
  history; Tab completes joint names.

The full HTTP/JSON API is documented in [`docs/api.md`](docs/api.md).

## Module map

| File | Purpose |
| --- | --- |
| `sts3215.py` | Low-level serial-bus driver (ping, read/write registers, move). |
| `buddy.py` | 6-joint wrapper: per-joint config, multi-joint moves, IK convenience method. |
| `kinematics.py` | Pure-Python forward and inverse kinematics. Tunable link-length constants. |
| `config.py` | `config.json` load/save (joints + Wi-Fi creds). |
| `wifi.py` | Connect to stored Wi-Fi; fall back to AP mode on failure. |
| `server.py` | Hand-rolled HTTP server. Serves `/www/` and exposes `/api/*`. |
| `www/` | Static UI bundle: `index.html`, `style.css`, `app.js`, `viewer.js`, `cli.js`, `pose.js`. |
| `setup_id.py` | One-shot utility for changing a servo's bus ID. |
| `calibrate.py` | Interactive joint-offset calibration; writes to `config.json`. |
| `tests/` | CPython tests (run on a dev machine, not the Pico). |

## Testing on a dev machine

The test suite stubs `machine` and `network` so the driver and helpers can
be exercised without hardware:

```
python -m pytest tests/
```

Run with coverage to keep an eye on the bar (the project targets ≥80 %):

```
python -m pytest tests/ --cov=. --cov-report=term-missing
```

## Troubleshooting

- **No reply from any servo.** Check power (7.4 V on the bus rail), the
  half-duplex direction pin (the driver board needs it for TX/RX
  switching), and that every servo has a unique ID. The `setup_id.py`
  comments cover the gotchas.
- **One servo replies, the rest don't.** Most likely two servos share an
  ID — re-run `setup_id.py` with one connected at a time.
- **Wi-Fi never joins.** Try the AP fallback to re-enter credentials. The
  `boot_network()` log on USB serial says exactly which path it took.
- **Web UI loads but sliders don't move the arm.** Check torque — the UI
  toggle defaults to whatever the device last had set. Some servos refuse
  goal-position writes when torque is off.
- **3D viewer is blank.** The page loads Three.js from a CDN; if the
  network blocks `unpkg.com` the viewer panel stays empty but the rest of
  the UI keeps working.
- **Pose target says "unreachable".** The arm has 5 effective DOF, so the
  yaw of the gripper must equal `atan2(y, x)` for off-axis targets. Leave
  the yaw input blank and let the server compute it.

## License

MIT — see `LICENSE` (if present) or treat the source as MIT-licensed.

---

This project began as the companion code for the YouTube video
*"Why are Bus Servos Better?"*; the standalone driver and demo scripts
(`demo.py`, `demo02.py`) still live in the repo as a minimal entry point.
