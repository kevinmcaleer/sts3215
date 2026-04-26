import json

from buddy import DEFAULT_JOINTS


CONFIG_PATH = "/config.json"


def default_config():
    """Return a fresh fallback config (joint defaults + empty wifi)."""
    return {
        "joints": {name: dict(j) for name, j in DEFAULT_JOINTS.items()},
        "wifi": {"ssid": "", "password": ""},
    }


def load_config(path=CONFIG_PATH):
    """Load config from flash, falling back to defaults on any failure."""
    try:
        with open(path) as f:
            return json.loads(f.read())
    except (OSError, ValueError) as e:
        print("config: falling back to defaults (" + str(e) + ")")
        return default_config()


def save_config(data, path=CONFIG_PATH):
    """Write config dict to flash as JSON."""
    with open(path, "w") as f:
        f.write(json.dumps(data))
