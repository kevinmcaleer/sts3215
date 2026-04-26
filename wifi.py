"""Wi-Fi connect with AP fallback for the Buddy arm.

At boot, `boot_network()` reads stored credentials, tries to join the
configured network, and falls back to access-point mode if that fails so
the user can provision new credentials over the web.
"""
import time

import network


def connect(ssid, password, timeout_s=15):
    """Join a Wi-Fi network. Returns IP on success, None on failure / no SSID."""
    if not ssid:
        return None
    sta = network.WLAN(network.STA_IF)
    sta.active(True)
    if not sta.isconnected():
        sta.connect(ssid, password)
        deadline = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
        while not sta.isconnected():
            if time.ticks_diff(deadline, time.ticks_ms()) <= 0:
                sta.disconnect()
                sta.active(False)
                return None
            time.sleep_ms(200)
    return sta.ifconfig()[0]


def start_ap(ssid="Buddy-Setup", password=None):
    """Bring up an access point. Open if password is missing or shorter than
    8 characters; WPA2 otherwise. Returns the AP IP address."""
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    if password and len(password) >= 8:
        ap.config(essid=ssid, password=password,
                  authmode=network.AUTH_WPA_WPA2_PSK)
    else:
        ap.config(essid=ssid, authmode=network.AUTH_OPEN)
    return ap.ifconfig()[0]


def boot_network(config_path="/config.json", ap_ssid="Buddy-Setup",
                 ap_password=None, connect_timeout_s=15):
    """Read creds from config; connect, or fall back to AP.

    Returns a dict: {"mode": "sta"|"ap", "ip": "...", "ssid": "..."}.
    """
    from config import load_config
    cfg = load_config(config_path)
    wifi_cfg = cfg.get("wifi") or {}
    ssid = wifi_cfg.get("ssid", "") or ""
    password = wifi_cfg.get("password", "") or ""

    if ssid:
        ip = connect(ssid, password, timeout_s=connect_timeout_s)
        if ip is not None:
            print("wifi: connected to {} as {}".format(ssid, ip))
            return {"mode": "sta", "ip": ip, "ssid": ssid}
        print("wifi: connect to {} failed; starting AP".format(ssid))
    else:
        print("wifi: no creds; starting AP")

    ap_ip = start_ap(ap_ssid, ap_password)
    print("wifi: AP {} at {}".format(ap_ssid, ap_ip))
    return {"mode": "ap", "ip": ap_ip, "ssid": ap_ssid}
