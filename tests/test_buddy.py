import time

import pytest

import config
from buddy import Buddy, DEFAULT_JOINTS
from sts3215 import degrees_to_position


class FakeBus:
    def __init__(self):
        self.moves = []
        self.torque = {}
        self.positions = {}
        self.alive = set()
        # moving_sequence[sid] is a list of values popped each read_moving call;
        # last value sticks once exhausted.
        self.moving_sequence = {}

    def ping(self, sid):
        return sid in self.alive

    def read_position(self, sid):
        return self.positions.get(sid)

    def move(self, sid, position, speed=0, acc=50):
        self.moves.append((sid, position, speed, acc))

    def set_torque(self, sid, enable):
        self.torque[sid] = bool(enable)

    def read_moving(self, sid):
        seq = self.moving_sequence.get(sid)
        if not seq:
            return 0
        return seq.pop(0) if len(seq) > 1 else seq[0]


def test_default_construction_uses_default_joints():
    b = Buddy(FakeBus())
    assert b.joints is DEFAULT_JOINTS


def test_explicit_joints_arg_wins():
    custom = {"only": {"id": 9, "min_deg": 0, "max_deg": 10, "offset_deg": 0, "sign": 1}}
    b = Buddy(FakeBus(), joints=custom)
    assert b.joints is custom


def test_config_path_loads_joints(tmp_path):
    path = str(tmp_path / "c.json")
    cfg = config.default_config()
    cfg["joints"]["base"]["max_deg"] = 123
    config.save_config(cfg, path)

    b = Buddy(FakeBus(), config_path=path)
    assert b.joints["base"]["max_deg"] == 123


def test_config_path_missing_falls_back_to_defaults(tmp_path):
    path = str(tmp_path / "missing.json")
    b = Buddy(FakeBus(), config_path=path)
    assert b.joints == config.default_config()["joints"]


def test_explicit_joints_beats_config_path(tmp_path):
    path = str(tmp_path / "c.json")
    config.save_config(config.default_config(), path)
    custom = {"only": {"id": 9, "min_deg": 0, "max_deg": 10, "offset_deg": 0, "sign": 1}}
    b = Buddy(FakeBus(), joints=custom, config_path=path)
    assert b.joints is custom


def test_ping_all_returns_status_per_joint():
    bus = FakeBus()
    bus.alive = {1, 3, 5}
    b = Buddy(bus)
    result = b.ping_all()
    assert result["base"] is True
    assert result["elbow"] is True
    assert result["shoulder"] is False


def test_move_joint_clamps_high(capsys):
    bus = FakeBus()
    custom = {"j": {"id": 1, "min_deg": 0, "max_deg": 90, "offset_deg": 0, "sign": 1}}
    b = Buddy(bus, joints=custom)
    b.move_joint("j", 200)
    out = capsys.readouterr().out
    assert "clamped" in out
    assert bus.moves[0][1] == degrees_to_position(90)


def test_move_joint_clamps_low(capsys):
    bus = FakeBus()
    custom = {"j": {"id": 1, "min_deg": 10, "max_deg": 90, "offset_deg": 0, "sign": 1}}
    b = Buddy(bus, joints=custom)
    b.move_joint("j", -5)
    assert bus.moves[0][1] == degrees_to_position(10)
    assert "clamped" in capsys.readouterr().out


def test_move_joint_unknown_raises():
    b = Buddy(FakeBus())
    with pytest.raises(KeyError):
        b.move_joint("nope", 0)


def test_move_joint_applies_offset_and_sign():
    bus = FakeBus()
    custom = {"j": {"id": 1, "min_deg": -180, "max_deg": 180, "offset_deg": 90, "sign": -1}}
    b = Buddy(bus, joints=custom)
    b.move_joint("j", 30)
    # raw_deg encoded = offset + sign * user = 90 + (-1)*30 = 60
    assert bus.moves[0][1] == degrees_to_position(60)


def test_read_all_positions_inverts_offset_and_sign():
    bus = FakeBus()
    custom = {"j": {"id": 1, "min_deg": -180, "max_deg": 180, "offset_deg": 90, "sign": -1}}
    bus.positions[1] = degrees_to_position(60)
    b = Buddy(bus, joints=custom)
    result = b.read_all_positions()
    assert result["j"] == pytest.approx(30, abs=0.1)


def test_read_all_positions_handles_none():
    bus = FakeBus()
    b = Buddy(bus)
    # No positions set → bus returns None for everything
    result = b.read_all_positions()
    assert all(v is None for v in result.values())


def test_move_all_iterates():
    bus = FakeBus()
    b = Buddy(bus)
    b.move_all({"base": 10, "elbow": 20})
    sids = [m[0] for m in bus.moves]
    assert sids == [DEFAULT_JOINTS["base"]["id"], DEFAULT_JOINTS["elbow"]["id"]]


def test_set_torque_all():
    bus = FakeBus()
    b = Buddy(bus)
    b.set_torque_all(True)
    assert all(v is True for v in bus.torque.values())
    assert set(bus.torque.keys()) == {j["id"] for j in DEFAULT_JOINTS.values()}
    b.set_torque_all(False)
    assert all(v is False for v in bus.torque.values())


def test_gripper_open_targets_max():
    bus = FakeBus()
    b = Buddy(bus)
    b.gripper_open()
    g = DEFAULT_JOINTS["gripper"]
    expected = degrees_to_position(g["offset_deg"] + g["sign"] * g["max_deg"])
    assert bus.moves[-1][1] == expected


def test_gripper_close_targets_min():
    bus = FakeBus()
    b = Buddy(bus)
    b.gripper_close()
    g = DEFAULT_JOINTS["gripper"]
    expected = degrees_to_position(g["offset_deg"] + g["sign"] * g["min_deg"])
    assert bus.moves[-1][1] == expected


# --- move_all_sync ---------------------------------------------------------


def _two_joint_buddy():
    bus = FakeBus()
    custom = {
        "a": {"id": 1, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign": 1},
        "b": {"id": 2, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign": 1},
    }
    bus.positions[1] = degrees_to_position(0)
    bus.positions[2] = degrees_to_position(0)
    return bus, Buddy(bus, joints=custom)


def test_move_all_sync_requires_one_of_duration_or_max_speed():
    _, b = _two_joint_buddy()
    with pytest.raises(ValueError):
        b.move_all_sync({"a": 10}, duration_ms=1000, max_speed=500)
    with pytest.raises(ValueError):
        b.move_all_sync({"a": 10})


def test_move_all_sync_rejects_non_positive_values():
    _, b = _two_joint_buddy()
    with pytest.raises(ValueError):
        b.move_all_sync({"a": 10}, duration_ms=0)
    with pytest.raises(ValueError):
        b.move_all_sync({"a": 10}, max_speed=0)


def test_move_all_sync_max_speed_scales_by_delta():
    bus, b = _two_joint_buddy()
    # a travels 90 deg, b travels 30 deg → b's speed is 1/3 of a's.
    b.move_all_sync({"a": 90, "b": 30}, max_speed=900)
    speeds = {sid: speed for sid, _, speed, _ in bus.moves}
    assert speeds[1] == 900
    assert speeds[2] == 300


def test_move_all_sync_duration_uses_delta_over_time():
    bus, b = _two_joint_buddy()
    bus.positions[1] = degrees_to_position(0)
    bus.positions[2] = degrees_to_position(0)
    # 90 deg = 1023 raw. duration 1000 ms → speed ≈ 1023 steps/sec.
    b.move_all_sync({"a": 90, "b": 30}, duration_ms=1000)
    speeds = {sid: speed for sid, _, speed, _ in bus.moves}
    a_raw = degrees_to_position(90)
    b_raw = degrees_to_position(30)
    assert speeds[1] == max(1, int(a_raw / 1.0))
    assert speeds[2] == max(1, int(b_raw / 1.0))


def test_move_all_sync_clamps_targets(capsys):
    bus = FakeBus()
    custom = {"j": {"id": 1, "min_deg": 0, "max_deg": 90, "offset_deg": 0, "sign": 1}}
    bus.positions[1] = degrees_to_position(0)
    b = Buddy(bus, joints=custom)
    b.move_all_sync({"j": 200}, max_speed=500)
    assert bus.moves[0][1] == degrees_to_position(90)
    assert "clamped" in capsys.readouterr().out


def test_move_all_sync_unknown_joint_raises():
    _, b = _two_joint_buddy()
    with pytest.raises(KeyError):
        b.move_all_sync({"nope": 10}, max_speed=500)


def test_move_all_sync_skips_joint_with_no_position(capsys):
    bus, b = _two_joint_buddy()
    bus.positions[2] = None  # b is offline / unreadable
    b.move_all_sync({"a": 90, "b": 30}, max_speed=900)
    sids = [sid for sid, *_ in bus.moves]
    assert sids == [1]
    assert "skip" in capsys.readouterr().out


def test_move_all_sync_zero_delta_still_issues_move_with_min_speed():
    bus, b = _two_joint_buddy()
    # a moves, b stays put.
    b.move_all_sync({"a": 90, "b": 0}, max_speed=900)
    speeds = {sid: speed for sid, _, speed, _ in bus.moves}
    assert speeds[1] == 900
    assert speeds[2] == 1  # min speed; bus.move still called for completeness


def test_move_all_sync_empty_plan_is_noop():
    bus = FakeBus()
    b = Buddy(bus, joints={"a": {"id": 1, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign": 1}})
    # No current position → the only joint is skipped → plan empty.
    b.move_all_sync({"a": 90}, max_speed=500)
    assert bus.moves == []


def test_move_all_sync_wait_polls_until_stopped():
    bus, b = _two_joint_buddy()
    bus.moving_sequence = {
        1: [1, 1, 0],
        2: [1, 0, 0],
    }
    b.move_all_sync({"a": 90, "b": 30}, max_speed=900,
                    wait=True, poll_interval_ms=0, timeout_ms=1000)
    # Both sequences exhausted to their terminal 0 → wait completed.
    assert bus.moving_sequence[1] == [0]
    assert bus.moving_sequence[2] == [0]


def test_move_all_sync_wait_skipped_when_no_motion():
    bus, b = _two_joint_buddy()
    # Both joints already at target — wait has nothing to poll.
    bus.moving_sequence = {1: [1], 2: [1]}  # would loop forever if polled
    b.move_all_sync({"a": 0, "b": 0}, max_speed=900,
                    wait=True, poll_interval_ms=0, timeout_ms=50)


def test_move_all_sync_wait_respects_timeout(monkeypatch):
    bus, b = _two_joint_buddy()
    bus.moving_sequence = {1: [1], 2: [1]}  # never reports stopped

    clock = {"t": 0}

    def fake_ticks_ms():
        clock["t"] += 100
        return clock["t"]

    monkeypatch.setattr(time, "ticks_ms", fake_ticks_ms)
    # With clock advancing 100 ms per call and timeout_ms=50, the deadline is
    # exceeded on the first loop check, so wait exits without hanging.
    b.move_all_sync({"a": 90, "b": 30}, max_speed=900,
                    wait=True, poll_interval_ms=0, timeout_ms=50)
