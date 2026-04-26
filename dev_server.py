"""Run the Buddy web UI on a dev machine — no Pico, no servos.

Stubs the MicroPython-only `machine` / `network` modules and replaces the
serial-bus driver with `SimBus`, which animates positions toward their
targets in software. The existing `Server` then runs on localhost so you
can drive the same UI bundle the device serves.

Usage:
    python3 dev_server.py            # http://127.0.0.1:8000
    python3 dev_server.py 9000       # custom port
    PORT=9000 python3 dev_server.py  # also fine
"""
import os
import sys
import time
import types


# --- MicroPython stubs (must run before any project imports) -------------

def _install_stubs():
    # Guard each install separately so the test conftest's richer stubs
    # (which track WLAN singletons for the wifi tests) aren't clobbered
    # when dev_server is imported in the test environment.
    if "machine" not in sys.modules:
        machine = types.ModuleType("machine")

        class _Pin:
            OUT = 1
            IN = 0
            def __init__(self, *a, **kw): pass
            def value(self, *a, **kw): pass

        class _UART:
            def __init__(self, *a, **kw): pass
            def read(self, n=None): return None
            def write(self, data): return len(data) if data else 0

        machine.Pin = _Pin
        machine.UART = _UART
        sys.modules["machine"] = machine

    if "network" not in sys.modules:
        network = types.ModuleType("network")
        network.STA_IF = 0
        network.AP_IF = 1
        network.AUTH_OPEN = 0
        network.AUTH_WPA_WPA2_PSK = 3

        class _WLAN:
            def __init__(self, *a, **kw): pass
            def active(self, *a, **kw): pass
            def isconnected(self): return False
            def ifconfig(self):
                return ("127.0.0.1", "255.255.255.0", "127.0.0.1", "127.0.0.1")
            def connect(self, *a, **kw): pass
            def disconnect(self): pass
            def config(self, **kw): pass

        network.WLAN = _WLAN
        sys.modules["network"] = network

    if not hasattr(time, "sleep_ms"):
        time.sleep_ms = lambda ms: time.sleep(ms / 1000.0)
    if not hasattr(time, "sleep_us"):
        time.sleep_us = lambda us: time.sleep(us / 1_000_000.0)
    if not hasattr(time, "ticks_ms"):
        time.ticks_ms = lambda: int(time.monotonic() * 1000)
    if not hasattr(time, "ticks_add"):
        time.ticks_add = lambda a, b: a + b
    if not hasattr(time, "ticks_diff"):
        time.ticks_diff = lambda a, b: a - b


_install_stubs()


# --- Project imports (now safe under CPython) ----------------------------

from buddy import Buddy, DEFAULT_JOINTS  # noqa: E402
from server import Server  # noqa: E402
from sts3215 import degrees_to_position  # noqa: E402


class SimBus:
    """Software-simulated STS3215 bus.

    Each call to read_position / read_moving advances the simulated motor
    toward its current target at a speed proportional to the last `move()`
    speed argument (with a sane default for speed=0). Torque is honoured —
    flipping torque off freezes positions where they are.
    """

    DEFAULT_STEPS_PER_SEC = 1500
    SPEED_TO_STEPS_PER_SEC = 50  # rough Feetech mapping

    def __init__(self, joint_ids=None, torque_default=True):
        ids = joint_ids or [j["id"] for j in DEFAULT_JOINTS.values()]
        now = time.monotonic()
        self._motors = {sid: {
            "current": float(degrees_to_position(0)),
            "target":  float(degrees_to_position(0)),
            "speed":   0,
            "torque":  bool(torque_default),
            "last_t":  now,
        } for sid in ids}

    # --- internal --------------------------------------------------------

    def _advance(self, sid):
        m = self._motors[sid]
        now = time.monotonic()
        dt = max(0.0, now - m["last_t"])
        m["last_t"] = now
        if not m["torque"]:
            return
        rate = (m["speed"] * self.SPEED_TO_STEPS_PER_SEC
                if m["speed"] > 0 else self.DEFAULT_STEPS_PER_SEC)
        diff = m["target"] - m["current"]
        step = rate * dt
        if abs(diff) <= step:
            m["current"] = m["target"]
        else:
            m["current"] += step if diff > 0 else -step

    # --- bus API used by Buddy / Server ---------------------------------

    def ping(self, sid):
        return sid in self._motors

    def read_position(self, sid):
        if sid not in self._motors:
            return None
        self._advance(sid)
        return int(self._motors[sid]["current"])

    def read_temperature(self, sid):
        return 32  # plausible idle temp

    def read_moving(self, sid):
        if sid not in self._motors:
            return None
        self._advance(sid)
        m = self._motors[sid]
        return 1 if int(m["current"]) != int(m["target"]) else 0

    def move(self, sid, position, speed=0, acc=50):
        if sid not in self._motors:
            return
        self._advance(sid)
        m = self._motors[sid]
        m["target"] = float(position)
        m["speed"] = int(speed) if speed else 0

    def set_torque(self, sid, enable):
        if sid in self._motors:
            self._advance(sid)
            self._motors[sid]["torque"] = bool(enable)


def main(argv=None):
    argv = sys.argv if argv is None else argv
    port = int(argv[1]) if len(argv) > 1 else int(os.environ.get("PORT", 8000))

    bus = SimBus()
    buddy = Buddy(bus)
    buddy.torque_enabled = True  # match the SimBus default so the UI pill agrees

    www_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "www")
    config_path = os.environ.get("BUDDY_CONFIG", "/tmp/buddy-dev-config.json")
    server = Server(buddy, www_root=www_root, config_path=config_path)

    print("sim arm: open http://127.0.0.1:{}/ in a browser".format(port))
    print("        torque starts ON; toggle in the UI to test the off path")
    print("        ctrl-c to stop")
    try:
        server.serve_forever(host="127.0.0.1", port=port)
    except KeyboardInterrupt:
        print("\nsim arm: stopped, port released")


if __name__ == "__main__":
    main()
