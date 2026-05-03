"""Tests for the command-line panel.

The CLI panel itself runs in the browser (www/cli.js), but the commands
map 1:1 to JSON API endpoints.  This module:

  1. Tests every CLI command path end-to-end through the Server, i.e.
     the exact payloads that cli.js would send for each command.
  2. Validates the /api/home endpoint added to support the `home` command.
  3. Tests edge cases: invalid commands, missing arguments, bad numbers.

This mirrors the command grammar defined in cli.js:

    move <joint> <degrees> [speed]
    pose <x> <y> <z> [roll pitch yaw]
    torque on|off
    gripper open|close|<percent>
    status
    home
"""
import json
import re

import pytest

from buddy import Buddy, DEFAULT_JOINTS
from server import Server
from sts3215 import degrees_to_position


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class FakeBus:
    def __init__(self):
        self.moves = []
        self.torque = {}
        self.positions = {sid: degrees_to_position(0)
                          for sid in (j["id"] for j in DEFAULT_JOINTS.values())}
        self.temps = {sid: 30 for sid in self.positions}

    def ping(self, sid):
        return True

    def read_position(self, sid):
        return self.positions.get(sid)

    def read_temperature(self, sid):
        return self.temps.get(sid)

    def move(self, sid, position, speed=0, acc=50):
        self.moves.append((sid, position, speed, acc))

    def set_torque(self, sid, enable):
        self.torque[sid] = bool(enable)

    def read_moving(self, sid):
        return 0


def _make_server():
    bus = FakeBus()
    buddy = Buddy(bus)
    server = Server(buddy, www_root="/nonexistent",
                    config_path="/nonexistent.json")
    return server, bus, buddy


def _call(server, method, path, body=b"", headers=None):
    return server.handle_request(method, path, headers or {}, body)


def _json(body):
    return json.loads(body.decode())


def _post(server, path, payload):
    """Shorthand for POSTing a JSON payload."""
    return _call(server, "POST", path,
                 json.dumps(payload).encode())


# ---------------------------------------------------------------------------
# CLI command: move <joint> <degrees> [speed]
#   maps to POST /api/joint/<name>  {degrees, speed?}
# ---------------------------------------------------------------------------

class TestCmdMove:

    def test_move_joint_with_degrees(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/joint/base", {"degrees": 45})
        assert status == 200
        assert _json(body)["ok"] is True
        base_id = DEFAULT_JOINTS["base"]["id"]
        assert any(m[0] == base_id for m in bus.moves)

    def test_move_joint_with_speed(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/joint/elbow",
                                {"degrees": 90, "speed": 500})
        assert status == 200
        elbow_id = DEFAULT_JOINTS["elbow"]["id"]
        sent = [m for m in bus.moves if m[0] == elbow_id]
        assert sent[0][2] == 500

    def test_move_unknown_joint_returns_404(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/joint/nonexistent",
                                {"degrees": 10})
        assert status == 404
        assert "unknown joint" in _json(body)["error"]

    def test_move_missing_degrees_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/joint/base", {"speed": 100})
        assert status == 400
        assert "degrees" in _json(body)["error"]

    def test_move_non_numeric_degrees_returns_400(self):
        server, _, _ = _make_server()
        status, _, _ = _post(server, "/api/joint/base",
                             {"degrees": "banana"})
        assert status == 400

    def test_move_all_joints(self):
        """Verify that every default joint can be targeted individually."""
        server, bus, _ = _make_server()
        for name, jcfg in DEFAULT_JOINTS.items():
            status, _, body = _post(server, "/api/joint/" + name,
                                    {"degrees": 10})
            assert status == 200, f"joint {name} failed"
            assert any(m[0] == jcfg["id"] for m in bus.moves)

    def test_move_zero_speed_defaults(self):
        server, bus, _ = _make_server()
        _post(server, "/api/joint/base", {"degrees": 30})
        base_id = DEFAULT_JOINTS["base"]["id"]
        sent = [m for m in bus.moves if m[0] == base_id]
        # Default speed is 0
        assert sent[0][2] == 0

    def test_move_with_acc(self):
        server, bus, _ = _make_server()
        _post(server, "/api/joint/base", {"degrees": 30, "acc": 100})
        base_id = DEFAULT_JOINTS["base"]["id"]
        sent = [m for m in bus.moves if m[0] == base_id]
        assert sent[0][3] == 100

    def test_move_url_encoded_joint_name(self):
        """Joint names with underscores should work through URL paths."""
        server, bus, _ = _make_server()
        status, _, _ = _post(server, "/api/joint/wrist_pitch",
                             {"degrees": 45})
        assert status == 200
        wp_id = DEFAULT_JOINTS["wrist_pitch"]["id"]
        assert any(m[0] == wp_id for m in bus.moves)


# ---------------------------------------------------------------------------
# CLI command: pose <x> <y> <z> [roll pitch yaw]
#   maps to POST /api/pose  {x, y, z, roll?, pitch?, yaw?}
# ---------------------------------------------------------------------------

class TestCmdPose:

    def test_pose_xyz_only(self):
        server, bus, _ = _make_server()
        from kinematics import L1, L2, L3, L4, L5
        status, _, _ = _post(server, "/api/pose",
                             {"x": 0, "y": 0, "z": L1 + L2 + L3 + L4 + L5})
        assert status == 200
        assert len(bus.moves) > 0

    def test_pose_with_orientation(self):
        server, _, _ = _make_server()
        from kinematics import L1, L2, L3, L4, L5
        status, _, _ = _post(server, "/api/pose", {
            "x": 0, "y": 0, "z": L1 + L2 + L3 + L4 + L5,
            "roll": 0, "pitch": 0, "yaw": 0,
        })
        assert status == 200

    def test_pose_unreachable_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/pose",
                                {"x": 99999, "y": 0, "z": 0})
        assert status == 400
        assert "unreachable" in _json(body)["error"]

    def test_pose_missing_coordinate_returns_400(self):
        server, _, _ = _make_server()
        # Missing z
        status, _, body = _post(server, "/api/pose", {"x": 0, "y": 0})
        assert status == 400
        assert "z" in _json(body)["error"]

    def test_pose_missing_x_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/pose", {"y": 0, "z": 100})
        assert status == 400
        assert "x" in _json(body)["error"]

    def test_pose_non_numeric_returns_400(self):
        server, _, _ = _make_server()
        status, _, _ = _post(server, "/api/pose",
                             {"x": "foo", "y": 0, "z": 0})
        assert status == 400


# ---------------------------------------------------------------------------
# CLI command: torque on|off
#   maps to POST /api/torque  {enable: bool}
# ---------------------------------------------------------------------------

class TestCmdTorque:

    def test_torque_on(self):
        server, _, buddy = _make_server()
        status, _, body = _post(server, "/api/torque", {"enable": True})
        assert status == 200
        assert _json(body)["torque_enabled"] is True
        assert buddy.torque_enabled is True

    def test_torque_off(self):
        server, _, buddy = _make_server()
        buddy.set_torque_all(True)
        status, _, body = _post(server, "/api/torque", {"enable": False})
        assert status == 200
        assert _json(body)["torque_enabled"] is False
        assert buddy.torque_enabled is False

    def test_torque_missing_enable_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/torque", {})
        assert status == 400
        assert "enable" in _json(body)["error"]


# ---------------------------------------------------------------------------
# CLI command: gripper open|close|<percent>
#   maps to POST /api/gripper  {state: "open"|"close"}
# ---------------------------------------------------------------------------

class TestCmdGripper:

    def test_gripper_open(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/gripper", {"state": "open"})
        assert status == 200
        assert _json(body)["ok"] is True
        gripper_id = DEFAULT_JOINTS["gripper"]["id"]
        assert any(m[0] == gripper_id for m in bus.moves)

    def test_gripper_close(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/gripper", {"state": "close"})
        assert status == 200
        gripper_id = DEFAULT_JOINTS["gripper"]["id"]
        assert any(m[0] == gripper_id for m in bus.moves)

    def test_gripper_invalid_state_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/gripper", {"state": "wave"})
        assert status == 400
        assert "open" in _json(body)["error"] or "close" in _json(body)["error"]

    def test_gripper_missing_state_returns_400(self):
        server, _, _ = _make_server()
        status, _, _ = _post(server, "/api/gripper", {})
        assert status == 400


# ---------------------------------------------------------------------------
# CLI command: status
#   maps to GET /api/status
# ---------------------------------------------------------------------------

class TestCmdStatus:

    def test_status_returns_positions(self):
        server, _, _ = _make_server()
        status, _, body = _call(server, "GET", "/api/status")
        assert status == 200
        data = _json(body)
        assert "positions" in data
        assert set(data["positions"].keys()) == set(DEFAULT_JOINTS.keys())

    def test_status_returns_temperatures(self):
        server, bus, _ = _make_server()
        bus.temps[DEFAULT_JOINTS["base"]["id"]] = 42
        status, _, body = _call(server, "GET", "/api/status")
        data = _json(body)
        assert data["temperatures"]["base"] == 42

    def test_status_returns_torque_state(self):
        server, _, buddy = _make_server()
        buddy.set_torque_all(True)
        _, _, body = _call(server, "GET", "/api/status")
        assert _json(body)["torque_enabled"] is True

    def test_status_torque_initially_none(self):
        server, _, _ = _make_server()
        _, _, body = _call(server, "GET", "/api/status")
        assert _json(body)["torque_enabled"] is None

    def test_status_via_post_returns_404(self):
        """status is GET-only; POST should not match."""
        server, _, _ = _make_server()
        status, _, _ = _call(server, "POST", "/api/status", b"{}")
        assert status == 404


# ---------------------------------------------------------------------------
# CLI command: home
#   maps to POST /api/home  {duration_ms?}
# ---------------------------------------------------------------------------

class TestCmdHome:

    def test_home_drives_all_arm_joints_to_zero(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/home", {})
        assert status == 200
        data = _json(body)
        assert data["ok"] is True
        # All arm joints (excluding gripper) should get a move to 0.
        expected_angles = {name: 0.0 for name in DEFAULT_JOINTS
                           if name != "gripper"}
        assert data["angles"] == expected_angles

    def test_home_with_duration_ms(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/home", {"duration_ms": 2000})
        assert status == 200
        assert _json(body)["ok"] is True
        # All arm joint IDs should have received move commands.
        arm_ids = {j["id"] for n, j in DEFAULT_JOINTS.items()
                   if n != "gripper"}
        moved_ids = {m[0] for m in bus.moves}
        assert arm_ids == moved_ids

    def test_home_with_include_gripper(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/home",
                                {"include_gripper": True})
        assert status == 200
        angles = _json(body)["angles"]
        assert "gripper" in angles
        assert angles["gripper"] == 0.0

    def test_home_excludes_gripper_by_default(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/home", {})
        assert status == 200
        angles = _json(body)["angles"]
        assert "gripper" not in angles

    def test_home_returns_501_when_buddy_lacks_home(self):
        """A Buddy-like object without .home triggers a 501."""
        class BareBuddy:
            joints = DEFAULT_JOINTS
            bus = FakeBus()
            torque_enabled = None
            def read_all_positions(self):
                return {n: 0.0 for n in DEFAULT_JOINTS}

        server = Server(BareBuddy())
        status, _, body = _post(server, "/api/home", {})
        assert status == 501
        assert "home" in _json(body)["error"]

    def test_home_with_max_speed(self):
        server, bus, _ = _make_server()
        status, _, body = _post(server, "/api/home",
                                {"max_speed": 400})
        assert status == 200
        assert _json(body)["ok"] is True
        # All speeds should be <= max_speed
        assert all(speed <= 400 for _, _, speed, _ in bus.moves)

    def test_home_default_duration(self):
        """When no duration_ms or max_speed is given, default is 1500ms."""
        server, bus, _ = _make_server()
        status, _, _ = _post(server, "/api/home", {})
        assert status == 200
        # Moves should have been issued (the default duration_ms=1500).
        assert len(bus.moves) > 0

    def test_home_via_get_returns_404(self):
        server, _, _ = _make_server()
        status, _, _ = _call(server, "GET", "/api/home")
        assert status == 404


# ---------------------------------------------------------------------------
# Error routing: unknown endpoints, bad JSON, wrong methods
# ---------------------------------------------------------------------------

class TestErrorHandling:

    def test_unknown_endpoint_returns_404(self):
        server, _, _ = _make_server()
        status, _, body = _post(server, "/api/nonexistent", {})
        assert status == 404
        assert "no such endpoint" in _json(body)["error"]

    def test_invalid_json_returns_400(self):
        server, _, _ = _make_server()
        status, _, body = _call(server, "POST", "/api/joint/base",
                                b"{not valid json")
        assert status == 400
        assert "invalid JSON" in _json(body)["error"]

    def test_empty_body_on_post_is_ok(self):
        """POST with an empty body should parse as an empty dict, not crash."""
        server, _, _ = _make_server()
        # /api/home accepts an empty body (all defaults)
        status, _, _ = _call(server, "POST", "/api/home", b"")
        assert status == 200

    def test_get_on_post_endpoint_returns_404(self):
        server, _, _ = _make_server()
        status, _, _ = _call(server, "GET", "/api/torque")
        assert status == 404


# ---------------------------------------------------------------------------
# CLI JavaScript asset: structural checks
# ---------------------------------------------------------------------------

class TestCliJsStructure:
    """Verify cli.js contains the right structure for all commands."""

    @pytest.fixture(autouse=True)
    def load_cli_js(self):
        import os
        cli_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "www", "cli.js")
        with open(cli_path, "r") as f:
            self.cli_source = f.read()

    def test_references_all_endpoints(self):
        for endpoint in ("/api/status", "/api/joint/", "/api/torque",
                         "/api/gripper", "/api/pose", "/api/home"):
            assert endpoint in self.cli_source, \
                f"cli.js missing endpoint reference: {endpoint}"

    def test_defines_all_commands(self):
        for cmd in ("move", "pose", "torque", "gripper", "status", "home"):
            assert cmd in self.cli_source, \
                f"cli.js missing command: {cmd}"

    def test_has_history_support(self):
        assert "ArrowUp" in self.cli_source
        assert "ArrowDown" in self.cli_source
        assert "history" in self.cli_source

    def test_has_tab_completion(self):
        assert "Tab" in self.cli_source
        assert "completeJoint" in self.cli_source

    def test_handles_unknown_commands(self):
        assert "unknown command" in self.cli_source

    def test_has_error_handling(self):
        assert "error" in self.cli_source

    def test_shows_usage_on_bad_args(self):
        assert "usage:" in self.cli_source

    def test_command_map_covers_all_commands(self):
        """The COMMANDS dict should have entries for all six commands."""
        for cmd in ("move", "pose", "torque", "gripper", "status", "home"):
            pattern = rf'^\s*{cmd}:\s+cmd'
            assert re.search(pattern, self.cli_source, re.MULTILINE), \
                f"COMMANDS map missing handler for: {cmd}"
