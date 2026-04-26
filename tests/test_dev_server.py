import time

import pytest

from dev_server import SimBus
from sts3215 import degrees_to_position


@pytest.fixture
def bus(monkeypatch):
    """SimBus with a mocked clock so we can advance time deterministically."""
    clock = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])
    b = SimBus()
    return b, clock


def test_initial_positions_are_home(bus):
    b, _ = bus
    for sid in (1, 2, 3, 4, 5, 6):
        assert b.read_position(sid) == degrees_to_position(0)


def test_ping_recognises_known_ids(bus):
    b, _ = bus
    assert b.ping(1) is True
    assert b.ping(99) is False


def test_unknown_id_returns_none(bus):
    b, _ = bus
    assert b.read_position(99) is None
    assert b.read_moving(99) is None


def test_move_animates_toward_target(bus):
    b, clock = bus
    target = degrees_to_position(90)
    b.move(1, target, speed=0)  # default rate
    # Immediately after move the simulation hasn't advanced.
    assert b.read_position(1) == 0
    # Advance ~0.5s — should be partway.
    clock["t"] = 0.5
    pos = b.read_position(1)
    assert 0 < pos < target
    # Advance well past the travel time — should clamp at target.
    clock["t"] = 10.0
    assert b.read_position(1) == target
    assert b.read_moving(1) == 0


def test_read_moving_is_one_until_arrival(bus):
    b, clock = bus
    b.move(1, degrees_to_position(180))
    clock["t"] = 0.05
    assert b.read_moving(1) == 1
    clock["t"] = 100.0
    assert b.read_moving(1) == 0


def test_speed_scales_animation_rate(bus):
    b, clock = bus
    fast_target = degrees_to_position(180)
    b.move(1, fast_target, speed=100)   # 100 * 50 = 5000 steps/sec
    b.move(2, fast_target, speed=10)    # 10  * 50 =  500 steps/sec
    clock["t"] = 0.1
    fast = b.read_position(1)
    slow = b.read_position(2)
    assert fast > slow


def test_torque_off_freezes_position(bus):
    b, clock = bus
    b.move(1, degrees_to_position(90))
    clock["t"] = 0.1
    pos_before = b.read_position(1)
    b.set_torque(1, False)
    clock["t"] = 5.0
    # Even after a long wait, position hasn't moved further.
    pos_after = b.read_position(1)
    assert pos_after == pos_before


def test_torque_on_resumes_motion(bus):
    b, clock = bus
    b.set_torque(1, False)
    b.move(1, degrees_to_position(90))
    clock["t"] = 5.0
    assert b.read_position(1) == 0  # torque off → no motion
    b.set_torque(1, True)
    clock["t"] = 100.0
    assert b.read_position(1) == degrees_to_position(90)


def test_buddy_drives_simbus_end_to_end(monkeypatch):
    """Smoke test: the same Buddy class the device uses works with SimBus."""
    clock = {"t": 0.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])

    from buddy import Buddy, DEFAULT_JOINTS
    bus = SimBus()
    buddy = Buddy(bus)
    buddy.move_joint("elbow", 45)
    clock["t"] = 100.0  # let the sim catch up
    positions = buddy.read_all_positions()
    assert positions["elbow"] == pytest.approx(45.0, abs=0.5)


def test_dev_server_main_smoke(monkeypatch):
    """main() should construct a server and call serve_forever — patch out
    the actual socket loop and verify wiring."""
    import dev_server
    captured = {}

    class _FakeServer:
        def __init__(self, buddy, www_root, config_path):
            captured["buddy"] = buddy
            captured["www_root"] = www_root
            captured["config_path"] = config_path

        def serve_forever(self, host, port):
            captured["host"] = host
            captured["port"] = port

    monkeypatch.setattr(dev_server, "Server", _FakeServer)
    dev_server.main(argv=["dev_server.py", "9123"])

    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == 9123
    assert captured["www_root"].endswith("/www")
    assert captured["buddy"].torque_enabled is True
