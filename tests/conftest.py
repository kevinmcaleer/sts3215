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
_install_time_ms_helpers()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
