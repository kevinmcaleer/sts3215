import time

import pytest

import config
import network
from wifi import boot_network, connect, start_ap


@pytest.fixture(autouse=True)
def _reset_network():
    network.WLAN.instances.clear()
    yield
    network.WLAN.instances.clear()


def test_connect_returns_none_for_empty_ssid():
    assert connect("", "anything") is None


def test_connect_skips_join_when_already_connected():
    sta = network.WLAN(network.STA_IF)
    sta._connected = True
    sta._ip = "10.0.0.5"
    assert connect("home", "pw") == "10.0.0.5"
    assert sta.connect_calls == []  # already connected → no join attempt


def test_connect_succeeds_after_a_few_polls(monkeypatch):
    sta = network.WLAN(network.STA_IF)
    poll_count = {"n": 0}
    real_isconnected = sta.isconnected

    def progressive_isconnected():
        poll_count["n"] += 1
        if poll_count["n"] >= 3:
            sta._connected = True
            sta._ip = "10.0.0.7"
        return real_isconnected()

    monkeypatch.setattr(sta, "isconnected", progressive_isconnected)
    assert connect("home", "pw", timeout_s=5) == "10.0.0.7"
    assert sta.connect_calls == [("home", "pw")]


def test_connect_returns_none_on_timeout(monkeypatch):
    clock = {"t": 0}

    def fake_ticks_ms():
        clock["t"] += 250
        return clock["t"]

    monkeypatch.setattr(time, "ticks_ms", fake_ticks_ms)

    sta = network.WLAN(network.STA_IF)
    assert connect("home", "wrong", timeout_s=1) is None
    assert sta.disconnect_calls >= 1
    assert sta.active_state is False


def test_start_ap_open_when_no_password():
    ip = start_ap("MyAP")
    ap = network.WLAN(network.AP_IF)
    assert ip == "192.168.4.1"
    assert ap._cfg.get("essid") == "MyAP"
    assert ap._cfg.get("authmode") == network.AUTH_OPEN
    assert "password" not in ap._cfg
    assert ap.active_state is True


def test_start_ap_secured_when_password_long_enough():
    start_ap("Secure", password="hunter22pw")
    ap = network.WLAN(network.AP_IF)
    assert ap._cfg.get("password") == "hunter22pw"
    assert ap._cfg.get("authmode") == network.AUTH_WPA_WPA2_PSK


def test_start_ap_open_when_password_too_short():
    start_ap("Short", password="abc")
    ap = network.WLAN(network.AP_IF)
    assert "password" not in ap._cfg
    assert ap._cfg.get("authmode") == network.AUTH_OPEN


def test_boot_network_connects_when_creds_present(tmp_path):
    cfg = config.default_config()
    cfg["wifi"] = {"ssid": "home", "password": "pw"}
    path = str(tmp_path / "config.json")
    config.save_config(cfg, path)

    sta = network.WLAN(network.STA_IF)
    sta._connected = True
    sta._ip = "10.0.0.42"

    result = boot_network(config_path=path)
    assert result == {"mode": "sta", "ip": "10.0.0.42", "ssid": "home"}


def test_boot_network_falls_back_to_ap_when_no_creds(tmp_path):
    cfg = config.default_config()
    cfg["wifi"] = {"ssid": "", "password": ""}
    path = str(tmp_path / "config.json")
    config.save_config(cfg, path)

    result = boot_network(config_path=path)
    assert result["mode"] == "ap"
    assert result["ip"] == "192.168.4.1"
    assert result["ssid"] == "Buddy-Setup"


def test_boot_network_falls_back_to_ap_when_connect_fails(tmp_path, monkeypatch):
    cfg = config.default_config()
    cfg["wifi"] = {"ssid": "wrong", "password": "wrong"}
    path = str(tmp_path / "config.json")
    config.save_config(cfg, path)

    clock = {"t": 0}

    def fake_ticks_ms():
        clock["t"] += 1000
        return clock["t"]

    monkeypatch.setattr(time, "ticks_ms", fake_ticks_ms)

    result = boot_network(config_path=path, connect_timeout_s=1)
    assert result["mode"] == "ap"
    assert result["ip"] == "192.168.4.1"


def test_boot_network_handles_missing_wifi_section(tmp_path):
    # Config file with no "wifi" key at all (older configs).
    path = str(tmp_path / "config.json")
    import json
    with open(path, "w") as f:
        f.write(json.dumps({"joints": {}}))

    result = boot_network(config_path=path)
    assert result["mode"] == "ap"


def test_boot_network_uses_custom_ap_settings(tmp_path):
    cfg = config.default_config()
    cfg["wifi"] = {"ssid": "", "password": ""}
    path = str(tmp_path / "config.json")
    config.save_config(cfg, path)

    result = boot_network(config_path=path,
                          ap_ssid="MyArm", ap_password="abcdefgh")
    assert result["ssid"] == "MyArm"
    ap = network.WLAN(network.AP_IF)
    assert ap._cfg.get("authmode") == network.AUTH_WPA_WPA2_PSK
