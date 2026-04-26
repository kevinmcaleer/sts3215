"""Stub MicroPython-only modules so tests can run on CPython."""
import os
import sys
import types


def _install_machine_stub():
    if "machine" in sys.modules:
        return
    machine = types.ModuleType("machine")

    class _Pin:
        OUT = 1
        IN = 0
        def __init__(self, *a, **kw): pass
        def value(self, *a, **kw): pass

    class _UART:
        def __init__(self, *a, **kw): self._buf = b""
        def read(self, n=None): return None
        def write(self, data): return len(data)

    machine.Pin = _Pin
    machine.UART = _UART
    sys.modules["machine"] = machine


def _install_network_stub():
    if "network" in sys.modules:
        return
    network = types.ModuleType("network")
    network.STA_IF = 0
    network.AP_IF = 1
    network.AUTH_OPEN = 0
    network.AUTH_WPA_WPA2_PSK = 3

    class _WLAN:
        instances = {}

        def __new__(cls, iface):
            if iface in cls.instances:
                return cls.instances[iface]
            obj = super().__new__(cls)
            cls.instances[iface] = obj
            obj._initialized = False
            return obj

        def __init__(self, iface):
            if self._initialized:
                return
            self._initialized = True
            self.iface = iface
            self.active_state = False
            self._connected = False
            self._ip = "0.0.0.0"
            self._cfg = {}
            self.connect_calls = []
            self.disconnect_calls = 0

        def active(self, state=None):
            if state is None:
                return self.active_state
            self.active_state = bool(state)

        def connect(self, ssid, password):
            self.connect_calls.append((ssid, password))

        def disconnect(self):
            self.disconnect_calls += 1
            self._connected = False

        def isconnected(self):
            return self._connected

        def ifconfig(self):
            return (self._ip, "255.255.255.0", "192.168.1.1", "8.8.8.8")

        def config(self, **kw):
            self._cfg.update(kw)
            if "essid" in kw and self.iface == network.AP_IF:
                self._ip = "192.168.4.1"

    network.WLAN = _WLAN
    sys.modules["network"] = network


def _install_time_ms_helpers():
    import time
    if not hasattr(time, "sleep_ms"):
        time.sleep_ms = lambda ms: None
    if not hasattr(time, "sleep_us"):
        time.sleep_us = lambda us: None
    if not hasattr(time, "ticks_ms"):
        time.ticks_ms = lambda: 0
    if not hasattr(time, "ticks_add"):
        time.ticks_add = lambda a, b: a + b
    if not hasattr(time, "ticks_diff"):
        time.ticks_diff = lambda a, b: a - b


_install_machine_stub()
_install_network_stub()
_install_time_ms_helpers()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
