import json
import os

import pytest

import config
from buddy import Buddy, DEFAULT_JOINTS
from server import Server, HttpError, _read_request, _write_response
from sts3215 import degrees_to_position


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

    def read_moving(self, sid):  # required by move_all_sync's wait branch
        return 0


def _make_server(www_root=None, config_path=None):
    bus = FakeBus()
    buddy = Buddy(bus)
    return Server(buddy,
                  www_root=www_root or "/nonexistent",
                  config_path=config_path or "/nonexistent.json"), bus, buddy


def _call(server, method, path, body=b"", headers=None):
    return server.handle_request(method, path, headers or {}, body)


def _json(body):
    return json.loads(body.decode())


# --- /api/status ---


def test_status_returns_positions_temps_and_torque_state():
    server, bus, buddy = _make_server()
    buddy.set_torque_all(True)
    bus.temps[DEFAULT_JOINTS["base"]["id"]] = 42

    status, headers, body = _call(server, "GET", "/api/status")
    assert status == 200
    assert ("Content-Type", "application/json") in headers
    payload = _json(body)
    assert set(payload["positions"].keys()) == set(DEFAULT_JOINTS.keys())
    assert payload["temperatures"]["base"] == 42
    assert payload["torque_enabled"] is True


def test_status_torque_unset_is_none():
    server, _, _ = _make_server()
    _, _, body = _call(server, "GET", "/api/status")
    assert _json(body)["torque_enabled"] is None


# --- /api/joint/<name> ---


def test_joint_post_moves_named_joint():
    server, bus, _ = _make_server()
    body = json.dumps({"degrees": 90, "speed": 200, "acc": 30}).encode()
    status, _, resp = _call(server, "POST", "/api/joint/elbow", body)
    assert status == 200
    assert _json(resp) == {"ok": True}
    elbow_id = DEFAULT_JOINTS["elbow"]["id"]
    sent = [m for m in bus.moves if m[0] == elbow_id]
    assert sent and sent[0][2] == 200 and sent[0][3] == 30


def test_joint_post_unknown_returns_404():
    server, _, _ = _make_server()
    body = json.dumps({"degrees": 10}).encode()
    status, _, resp = _call(server, "POST", "/api/joint/nope", body)
    assert status == 404
    assert "unknown joint" in _json(resp)["error"]


def test_joint_post_missing_degrees_returns_400():
    server, _, _ = _make_server()
    body = json.dumps({"speed": 0}).encode()
    status, _, resp = _call(server, "POST", "/api/joint/elbow", body)
    assert status == 400
    assert "degrees" in _json(resp)["error"]


def test_joint_post_non_numeric_degrees_returns_400():
    server, _, _ = _make_server()
    body = json.dumps({"degrees": "not-a-number"}).encode()
    status, _, _resp = _call(server, "POST", "/api/joint/elbow", body)
    assert status == 400


# --- /api/move ---


def test_move_calls_move_all_when_no_pace_specified():
    server, bus, _ = _make_server()
    body = json.dumps({"joints": {"base": 30, "elbow": 60}}).encode()
    status, _, _ = _call(server, "POST", "/api/move", body)
    assert status == 200
    sids = [m[0] for m in bus.moves]
    assert DEFAULT_JOINTS["base"]["id"] in sids
    assert DEFAULT_JOINTS["elbow"]["id"] in sids


def test_move_uses_max_speed_when_provided():
    server, bus, _ = _make_server()
    body = json.dumps({"joints": {"base": 30, "elbow": 60},
                       "max_speed": 800}).encode()
    status, _, _ = _call(server, "POST", "/api/move", body)
    assert status == 200
    # All emitted speeds should be ≤ max_speed.
    assert bus.moves
    assert all(speed <= 800 for _, _, speed, _ in bus.moves)


def test_move_returns_400_when_joints_missing():
    server, _, _ = _make_server()
    body = json.dumps({}).encode()
    status, _, _ = _call(server, "POST", "/api/move", body)
    assert status == 400


def test_move_returns_400_for_invalid_pacing():
    server, _, _ = _make_server()
    body = json.dumps({"joints": {"base": 0},
                       "duration_ms": 1000,
                       "max_speed": 500}).encode()
    status, _, resp = _call(server, "POST", "/api/move", body)
    assert status == 400
    assert "exactly one" in _json(resp)["error"]


# --- /api/pose ---


def test_pose_reachable_target_drives_arm():
    server, bus, _ = _make_server()
    from kinematics import L1, L2, L3, L4, L5
    body = json.dumps({"x": 0, "y": 0, "z": L1 + L2 + L3 + L4 + L5}).encode()
    status, _, _ = _call(server, "POST", "/api/pose", body)
    assert status == 200
    # Five arm joints should have received move commands.
    assert len({m[0] for m in bus.moves}) == 5


def test_pose_unreachable_returns_400():
    server, _, _ = _make_server()
    body = json.dumps({"x": 99999, "y": 0, "z": 0}).encode()
    status, _, resp = _call(server, "POST", "/api/pose", body)
    assert status == 400
    assert "unreachable" in _json(resp)["error"]


def test_pose_missing_xyz_returns_400():
    server, _, _ = _make_server()
    body = json.dumps({"x": 0, "y": 0}).encode()  # z missing
    status, _, resp = _call(server, "POST", "/api/pose", body)
    assert status == 400
    assert "z" in _json(resp)["error"]


def test_pose_non_numeric_returns_400():
    server, _, _ = _make_server()
    body = json.dumps({"x": "a", "y": 0, "z": 0}).encode()
    status, _, _ = _call(server, "POST", "/api/pose", body)
    assert status == 400


# --- /api/gripper, /api/torque ---


def test_gripper_open_close():
    server, bus, _ = _make_server()
    _call(server, "POST", "/api/gripper", json.dumps({"state": "open"}).encode())
    _call(server, "POST", "/api/gripper", json.dumps({"state": "close"}).encode())
    gripper_id = DEFAULT_JOINTS["gripper"]["id"]
    assert any(m[0] == gripper_id for m in bus.moves)


def test_gripper_invalid_state_returns_400():
    server, _, _ = _make_server()
    status, _, _ = _call(server, "POST", "/api/gripper",
                         json.dumps({"state": "wave"}).encode())
    assert status == 400


def test_torque_enable_and_disable():
    server, _, buddy = _make_server()
    status, _, resp = _call(server, "POST", "/api/torque",
                            json.dumps({"enable": True}).encode())
    assert status == 200
    assert _json(resp)["torque_enabled"] is True
    assert buddy.torque_enabled is True

    _call(server, "POST", "/api/torque",
          json.dumps({"enable": False}).encode())
    assert buddy.torque_enabled is False


def test_torque_missing_enable_returns_400():
    server, _, _ = _make_server()
    status, _, _ = _call(server, "POST", "/api/torque", b"{}")
    assert status == 400


# --- /api/wifi (provisioning) ---


def test_wifi_post_writes_config(tmp_path):
    cfg_path = str(tmp_path / "config.json")
    config.save_config(config.default_config(), cfg_path)
    bus = FakeBus()
    server = Server(Buddy(bus), config_path=cfg_path)
    body = json.dumps({"ssid": "home", "password": "letmein"}).encode()
    status, _, _ = _call(server, "POST", "/api/wifi", body)
    assert status == 200
    saved = config.load_config(cfg_path)
    assert saved["wifi"] == {"ssid": "home", "password": "letmein"}


def test_wifi_missing_ssid_returns_400(tmp_path):
    cfg_path = str(tmp_path / "config.json")
    config.save_config(config.default_config(), cfg_path)
    bus = FakeBus()
    server = Server(Buddy(bus), config_path=cfg_path)
    status, _, _ = _call(server, "POST", "/api/wifi",
                         json.dumps({"password": "x"}).encode())
    assert status == 400


# --- routing / framing ---


def test_invalid_json_body_returns_400():
    server, _, _ = _make_server()
    status, _, resp = _call(server, "POST", "/api/joint/elbow", b"{nope")
    assert status == 400
    assert "invalid JSON" in _json(resp)["error"]


def test_unknown_endpoint_returns_404():
    server, _, _ = _make_server()
    status, _, _ = _call(server, "POST", "/api/wat", b"")
    assert status == 404


def test_method_not_allowed_for_get_on_post_endpoint():
    server, _, _ = _make_server()
    # GET against /api/move should 404 since route only matches on POST.
    status, _, _ = _call(server, "GET", "/api/move")
    assert status == 404


# --- static file serving ---


def test_static_serves_index_html(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    (www / "index.html").write_text("<h1>hi</h1>")
    server, _, _ = _make_server(www_root=str(www))
    status, headers, body = _call(server, "GET", "/")
    assert status == 200
    assert ("Content-Type", "text/html") in headers
    assert body == b"<h1>hi</h1>"


def test_static_serves_js_with_correct_content_type(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    (www / "app.js").write_text("var x;")
    server, _, _ = _make_server(www_root=str(www))
    status, headers, body = _call(server, "GET", "/app.js")
    assert status == 200
    assert ("Content-Type", "application/javascript") in headers


def test_static_missing_returns_404(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    server, _, _ = _make_server(www_root=str(www))
    status, _, _ = _call(server, "GET", "/missing.html")
    assert status == 404


def test_static_blocks_path_traversal(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    (www / "ok.html").write_text("ok")
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    server, _, _ = _make_server(www_root=str(www))
    status, _, _ = _call(server, "GET", "/../secret.txt")
    assert status == 400


def test_static_unknown_extension_falls_back_to_octet_stream(tmp_path):
    www = tmp_path / "www"
    www.mkdir()
    (www / "blob").write_bytes(b"\x00\x01\x02")
    server, _, _ = _make_server(www_root=str(www))
    status, headers, _ = _call(server, "GET", "/blob")
    assert status == 200
    assert ("Content-Type", "application/octet-stream") in headers


def test_post_to_static_path_returns_405():
    server, _, _ = _make_server()
    status, _, _ = _call(server, "POST", "/index.html", b"")
    assert status == 405


# --- handle_connection (request/response framing) ---


class FakeConn:
    def __init__(self, request_bytes):
        self._buf = request_bytes
        self.sent = b""
        self.closed = False

    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    def send(self, data):
        self.sent += data

    def close(self):
        self.closed = True


def test_handle_connection_round_trip():
    server, _, _ = _make_server()
    req = (b"GET /api/status HTTP/1.0\r\n"
           b"Host: x\r\n\r\n")
    conn = FakeConn(req)
    server.handle_connection(conn)
    assert conn.sent.startswith(b"HTTP/1.0 200 OK\r\n")
    assert b"\"positions\"" in conn.sent
    assert conn.closed


def test_handle_connection_with_post_body():
    server, _, _ = _make_server()
    payload = json.dumps({"enable": True}).encode()
    req = (b"POST /api/torque HTTP/1.0\r\n"
           b"Content-Length: " + str(len(payload)).encode() + b"\r\n"
           b"Content-Type: application/json\r\n\r\n" + payload)
    conn = FakeConn(req)
    server.handle_connection(conn)
    assert b"200 OK" in conn.sent
    assert b"\"torque_enabled\": true" in conn.sent


def test_handle_connection_handles_premature_close():
    server, _, _ = _make_server()
    conn = FakeConn(b"")  # peer closed before sending anything
    server.handle_connection(conn)
    assert conn.sent == b""
    assert conn.closed


def test_read_request_returns_none_for_malformed_request_line():
    conn = FakeConn(b"NOPE\r\n\r\n")
    assert _read_request(conn) is None


def test_read_request_streams_long_body_across_recvs():
    payload = b"x" * 3000  # bigger than 1024 recv chunk
    req = (b"POST /api/joint/elbow HTTP/1.0\r\n"
           b"Content-Length: " + str(len(payload)).encode() + b"\r\n\r\n"
           + payload)
    conn = FakeConn(req)
    method, path, headers, body = _read_request(conn)
    assert method == "POST"
    assert path == "/api/joint/elbow"
    assert len(body) == len(payload)


def test_pose_with_explicit_yaw_passes_through():
    server, _, _ = _make_server()
    from kinematics import L1, L2, L3, L4, L5
    body = json.dumps({"x": 0, "y": 0, "z": L1 + L2 + L3 + L4 + L5,
                       "yaw": 30.0}).encode()
    status, _, _ = _call(server, "POST", "/api/pose", body)
    assert status == 200


def test_pose_returns_501_when_buddy_lacks_move_to_pose():
    # A bare buddy stand-in without move_to_pose triggers the 501 branch.
    class BareBuddy:
        joints = DEFAULT_JOINTS
        bus = FakeBus()
        torque_enabled = None
        def read_all_positions(self): return {n: 0.0 for n in DEFAULT_JOINTS}

    server = Server(BareBuddy())
    body = json.dumps({"x": 0, "y": 0, "z": 100}).encode()
    status, _, resp = _call(server, "POST", "/api/pose", body)
    assert status == 501
    assert "move_to_pose" in _json(resp)["error"]


def test_status_handles_bus_without_read_temperature():
    class BareBus:
        def __init__(self):
            self.positions = {sid: 0 for sid in
                              (j["id"] for j in DEFAULT_JOINTS.values())}

        def ping(self, sid): return True
        def read_position(self, sid): return self.positions.get(sid)
        def move(self, sid, position, speed=0, acc=50): pass
        def set_torque(self, sid, enable): pass

    server = Server(Buddy(BareBus()))
    status, _, body = _call(server, "GET", "/api/status")
    assert status == 200
    temps = _json(body)["temperatures"]
    assert all(v is None for v in temps.values())
