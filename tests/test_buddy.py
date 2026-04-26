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

    def ping(self, sid):
        return sid in self.alive

    def read_position(self, sid):
        return self.positions.get(sid)

    def move(self, sid, position, speed=0, acc=50):
        self.moves.append((sid, position, speed, acc))

    def set_torque(self, sid, enable):
        self.torque[sid] = bool(enable)


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
