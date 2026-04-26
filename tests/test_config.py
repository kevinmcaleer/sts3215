import json
import os

import pytest

import config
from buddy import DEFAULT_JOINTS


def test_default_config_has_all_joints_and_wifi():
    cfg = config.default_config()
    assert set(cfg["joints"].keys()) == set(DEFAULT_JOINTS.keys())
    assert cfg["wifi"] == {"ssid": "", "password": ""}


def test_default_config_does_not_share_joint_dicts_with_module_constant():
    cfg = config.default_config()
    cfg["joints"]["base"]["offset_deg"] = 99
    assert DEFAULT_JOINTS["base"]["offset_deg"] == 0


def test_save_and_load_round_trip(tmp_path):
    path = str(tmp_path / "config.json")
    cfg = config.default_config()
    cfg["wifi"]["ssid"] = "home"
    cfg["wifi"]["password"] = "hunter2"
    cfg["joints"]["elbow"]["offset_deg"] = 12.5

    config.save_config(cfg, path)
    loaded = config.load_config(path)

    assert loaded == cfg


def test_load_missing_file_falls_back_to_defaults(tmp_path, capsys):
    path = str(tmp_path / "nope.json")
    loaded = config.load_config(path)
    assert loaded == config.default_config()
    out = capsys.readouterr().out
    assert "falling back" in out


def test_load_invalid_json_falls_back_to_defaults(tmp_path, capsys):
    path = str(tmp_path / "bad.json")
    with open(path, "w") as f:
        f.write("{not valid json")
    loaded = config.load_config(path)
    assert loaded == config.default_config()
    out = capsys.readouterr().out
    assert "falling back" in out


def test_save_writes_valid_json(tmp_path):
    path = str(tmp_path / "out.json")
    config.save_config({"a": 1, "b": [2, 3]}, path)
    with open(path) as f:
        assert json.loads(f.read()) == {"a": 1, "b": [2, 3]}
