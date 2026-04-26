"""Smoke tests that the bundled web UI files load through Server."""
import json
import os

import pytest

from buddy import Buddy, DEFAULT_JOINTS
from server import Server
from sts3215 import degrees_to_position


WWW_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "www")


class _Bus:
    def __init__(self):
        self.positions = {sid: degrees_to_position(0)
                          for sid in (j["id"] for j in DEFAULT_JOINTS.values())}

    def ping(self, sid): return True
    def read_position(self, sid): return self.positions.get(sid)
    def read_temperature(self, sid): return 30
    def move(self, sid, p, speed=0, acc=50): pass
    def set_torque(self, sid, enable): pass


def _server():
    return Server(Buddy(_Bus()), www_root=WWW_DIR)


@pytest.mark.parametrize("path,marker,content_type", [
    ("/",          b"<title>Buddy", "text/html"),
    ("/style.css", b".joint",       "text/css"),
    ("/app.js",    b"/api/status",  "application/javascript"),
    ("/viewer.js", b"three",        "application/javascript"),
    ("/cli.js",    b"/api/status",  "application/javascript"),
])
def test_static_bundle_is_reachable(path, marker, content_type):
    status, headers, body = _server().handle_request("GET", path, {}, b"")
    assert status == 200
    assert (("Content-Type", content_type)) in headers
    assert marker in body


def test_app_js_references_each_arm_endpoint():
    with open(os.path.join(WWW_DIR, "app.js"), "rb") as f:
        body = f.read()
    for endpoint in (b"/api/status", b"/api/joint/", b"/api/torque",
                     b"/api/gripper"):
        assert endpoint in body, "app.js missing " + endpoint.decode()


def test_index_html_wires_in_viewer():
    with open(os.path.join(WWW_DIR, "index.html"), "rb") as f:
        body = f.read()
    assert b"viewer.js" in body, "index.html missing viewer.js script tag"
    assert b"importmap" in body, "index.html missing importmap"
    assert b"three" in body and b"unpkg.com/three" in body, \
        "index.html importmap missing three CDN entry"
    assert b'id="viewer"' in body, "index.html missing #viewer container"


def test_cli_js_references_each_endpoint_it_drives():
    with open(os.path.join(WWW_DIR, "cli.js"), "rb") as f:
        body = f.read()
    for endpoint in (b"/api/status", b"/api/joint/", b"/api/torque",
                     b"/api/gripper", b"/api/pose", b"/api/move"):
        assert endpoint in body, "cli.js missing " + endpoint.decode()


def test_index_html_loads_cli_js():
    with open(os.path.join(WWW_DIR, "index.html"), "rb") as f:
        body = f.read()
    assert b"cli.js" in body, "index.html does not reference cli.js"
