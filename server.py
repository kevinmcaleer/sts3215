"""Lightweight HTTP/JSON server for the Buddy arm.

Hand-rolled on top of `socket` (MicroPython-friendly — no third-party
deps). Serves static files from `www_root` and exposes a JSON API:

  GET  /api/status            → joint angles, torque state, temperatures
  POST /api/joint/<name>      → {degrees, speed?, acc?}
  POST /api/move              → {joints: {...}, duration_ms?, max_speed?}
  POST /api/pose              → {x, y, z, roll?, pitch?, yaw?, duration_ms?}
  POST /api/gripper           → {state: "open"|"close"}
  POST /api/torque            → {enable: bool}
  POST /api/wifi              → {ssid, password}    (provisioning)

All responses are JSON. Errors return {"error": "..."} with an
appropriate status code.
"""
import json


CONTENT_TYPES = {
    "html": "text/html",
    "css":  "text/css",
    "js":   "application/javascript",
    "json": "application/json",
    "png":  "image/png",
    "jpg":  "image/jpeg",
    "svg":  "image/svg+xml",
    "ico":  "image/x-icon",
}

STATUS_TEXT = {
    200: "OK",
    400: "Bad Request",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


class HttpError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message


def _json_response(body, status=200):
    return (status,
            [("Content-Type", "application/json")],
            json.dumps(body).encode())


def _bytes_response(data, content_type, status=200):
    return (status, [("Content-Type", content_type)], data)


def _read_request(conn):
    """Read an HTTP request from conn. Returns (method, path, headers, body)
    or None if the peer closed before a full request arrived."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(1024)
        if not chunk:
            return None
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    parts = lines[0].decode().split(" ", 2)
    if len(parts) < 2:
        return None
    method = parts[0]
    path = parts[1]
    headers = {}
    for line in lines[1:]:
        k, _, v = line.decode().partition(":")
        if k:
            headers[k.strip().lower()] = v.strip()
    body = rest
    content_length = int(headers.get("content-length", "0") or "0")
    while len(body) < content_length:
        chunk = conn.recv(1024)
        if not chunk:
            break
        body += chunk
    return method, path, headers, body


def _write_response(conn, status, headers, body):
    head = "HTTP/1.0 {} {}\r\n".format(status, STATUS_TEXT.get(status, "OK"))
    head += "Content-Length: {}\r\n".format(len(body))
    head += "Connection: close\r\n"
    for k, v in headers:
        head += "{}: {}\r\n".format(k, v)
    head += "\r\n"
    conn.send(head.encode() + body)


class Server:
    def __init__(self, buddy, www_root="/www", config_path="/config.json"):
        self.buddy = buddy
        self.www_root = www_root
        self.config_path = config_path

    def handle_request(self, method, path, headers, body):
        try:
            if path.startswith("/api/"):
                return self._handle_api(method, path, body)
            if method == "GET":
                return self._handle_static(path)
            return _json_response({"error": "method not allowed"}, 405)
        except HttpError as e:
            return _json_response({"error": e.message}, e.status)
        except Exception as e:  # pragma: no cover - defensive top-level catch
            return _json_response(
                {"error": "internal error", "detail": str(e)}, 500)

    def _handle_api(self, method, path, body):
        data = {}
        if body:
            try:
                data = json.loads(body)
            except (ValueError, TypeError):
                raise HttpError(400, "invalid JSON")

        if path == "/api/status" and method == "GET":
            return self._status()
        if path == "/api/move" and method == "POST":
            return self._move(data)
        if path == "/api/pose" and method == "POST":
            return self._pose(data)
        if path == "/api/ik" and method == "POST":
            return self._ik(data)
        if path == "/api/gripper" and method == "POST":
            return self._gripper(data)
        if path == "/api/torque" and method == "POST":
            return self._torque(data)
        if path == "/api/home" and method == "POST":
            return self._home(data)
        if path == "/api/wifi" and method == "POST":
            return self._wifi(data)
        if path.startswith("/api/joint/") and method == "POST":
            return self._joint(path[len("/api/joint/"):], data)
        raise HttpError(404, "no such endpoint: " + path)

    def _status(self):
        positions = self.buddy.read_all_positions()
        temps = {}
        for name, j in self.buddy.joints.items():
            try:
                temps[name] = self.buddy.bus.read_temperature(j["id"])
            except AttributeError:
                temps[name] = None
        return _json_response({
            "positions": positions,
            "temperatures": temps,
            "torque_enabled": self.buddy.torque_enabled,
        })

    def _joint(self, name, data):
        if "degrees" not in data:
            raise HttpError(400, "missing 'degrees'")
        try:
            degrees = float(data["degrees"])
        except (TypeError, ValueError):
            raise HttpError(400, "'degrees' must be a number")
        speed = int(data.get("speed", 0) or 0)
        acc = int(data.get("acc", 50) or 0)
        try:
            self.buddy.move_joint(name, degrees, speed=speed, acc=acc)
        except KeyError:
            raise HttpError(404, "unknown joint: " + name)
        return _json_response({"ok": True})

    def _move(self, data):
        joints = data.get("joints")
        if not isinstance(joints, dict) or not joints:
            raise HttpError(400, "missing or empty 'joints' object")
        duration_ms = data.get("duration_ms")
        max_speed = data.get("max_speed")
        if duration_ms is not None or max_speed is not None:
            try:
                self.buddy.move_all_sync(joints, duration_ms=duration_ms,
                                         max_speed=max_speed)
            except ValueError as e:
                raise HttpError(400, str(e))
        else:
            self.buddy.move_all(joints)
        return _json_response({"ok": True})

    def _pose(self, data):
        for k in ("x", "y", "z"):
            if k not in data:
                raise HttpError(400, "missing '{}'".format(k))
        try:
            x = float(data["x"])
            y = float(data["y"])
            z = float(data["z"])
        except (TypeError, ValueError):
            raise HttpError(400, "x, y, z must be numbers")
        roll = float(data.get("roll", 0.0))
        pitch = float(data.get("pitch", 0.0))
        yaw = data.get("yaw")
        if yaw is not None:
            yaw = float(yaw)
        if not hasattr(self.buddy, "move_to_pose"):
            raise HttpError(501, "pose endpoint requires Buddy.move_to_pose")
        try:
            angles = self.buddy.move_to_pose(
                x, y, z, roll=roll, pitch=pitch, yaw=yaw,
                duration_ms=data.get("duration_ms"),
                max_speed=data.get("max_speed"))
        except ValueError as e:
            raise HttpError(400, str(e))
        # Return the joint targets so the UI can apply them optimistically
        # before the arm finishes moving. Older callers ignore the field.
        return _json_response({"ok": True, "angles": angles or {}})

    def _ik(self, data):
        for k in ("x", "y", "z"):
            if k not in data:
                raise HttpError(400, "missing '{}'".format(k))
        try:
            x = float(data["x"]); y = float(data["y"]); z = float(data["z"])
        except (TypeError, ValueError):
            raise HttpError(400, "x, y, z must be numbers")
        roll = float(data.get("roll", 0.0))
        pitch = float(data.get("pitch", 0.0))
        yaw = data.get("yaw")
        if yaw is None:
            import math as _m
            yaw = _m.degrees(_m.atan2(y, x))
        else:
            yaw = float(yaw)
        try:
            from kinematics import inverse_kinematics
        except ImportError:
            raise HttpError(501, "kinematics module unavailable")
        angles = inverse_kinematics((x, y, z, roll, pitch, yaw),
                                    elbow_up=bool(data.get("elbow_up", False)))
        if angles is None:
            return _json_response(
                {"reachable": False, "error": "pose unreachable"}, 400)
        # Drop the gripper entry — the pose doesn't constrain it.
        angles = {n: v for n, v in angles.items() if n != "gripper"}
        return _json_response({"reachable": True, "angles": angles})

    def _gripper(self, data):
        state = data.get("state")
        if state == "open":
            self.buddy.gripper_open()
        elif state == "close":
            self.buddy.gripper_close()
        else:
            raise HttpError(400, "state must be 'open' or 'close'")
        return _json_response({"ok": True})

    def _torque(self, data):
        if "enable" not in data:
            raise HttpError(400, "missing 'enable'")
        self.buddy.set_torque_all(bool(data["enable"]))
        return _json_response({"ok": True, "torque_enabled":
                               self.buddy.torque_enabled})

    def _home(self, data):
        if not hasattr(self.buddy, "home"):
            raise HttpError(501, "buddy.home not available")
        duration_ms = data.get("duration_ms", 1500)
        max_speed = data.get("max_speed")
        include_gripper = bool(data.get("include_gripper", False))
        try:
            angles = self.buddy.home(duration_ms=duration_ms,
                                     max_speed=max_speed,
                                     include_gripper=include_gripper)
        except ValueError as e:
            raise HttpError(400, str(e))
        return _json_response({"ok": True, "angles": angles or {}})

    def _wifi(self, data):
        ssid = (data.get("ssid") or "").strip()
        password = data.get("password") or ""
        if not ssid:
            raise HttpError(400, "missing 'ssid'")
        from config import load_config, save_config
        cfg = load_config(self.config_path)
        cfg["wifi"] = {"ssid": ssid, "password": password}
        save_config(cfg, self.config_path)
        return _json_response({"ok": True, "saved": True})

    def _handle_static(self, path):
        if path in ("", "/"):
            path = "/index.html"
        rel = path.lstrip("/")
        if ".." in rel.split("/"):
            raise HttpError(400, "bad path")
        full = self.www_root + "/" + rel
        try:
            with open(full, "rb") as f:
                data = f.read()
        except OSError:
            raise HttpError(404, "not found: " + path)
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        return _bytes_response(data,
                               CONTENT_TYPES.get(ext, "application/octet-stream"))

    def handle_connection(self, conn):
        """Read one request from conn and write one response. Closes conn."""
        try:
            req = _read_request(conn)
            if req is None:
                return
            method, path, headers, body = req
            status, hdrs, body_out = self.handle_request(
                method, path, headers, body)
            _write_response(conn, status, hdrs, body_out)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def serve_forever(self, host="0.0.0.0", port=80):  # pragma: no cover
        import socket
        sock = socket.socket()
        # Allow rebinding immediately after the previous run exited — without
        # this, the OS keeps the port in TIME_WAIT for ~30 s on CPython.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except (AttributeError, OSError):
            pass  # MicroPython ports without SO_REUSEADDR — ignore.
        try:
            sock.bind((host, port))
            sock.listen(5)
            print("server: listening on {}:{}".format(host, port))
            while True:
                conn, _addr = sock.accept()
                try:
                    self.handle_connection(conn)
                except Exception as e:
                    print("server: error", e)
        finally:
            try:
                sock.close()
            except Exception:
                pass
