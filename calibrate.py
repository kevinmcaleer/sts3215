from sts3215 import STS3215
from buddy import Buddy
from config import default_config, load_config, save_config, CONFIG_PATH


bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy = Buddy(bus, config_path=CONFIG_PATH)

buddy.set_torque_all(False)
print("Pose the arm to its zero position, then press ENTER.")
input()

captured = buddy.read_all_positions()
print("Captured:", captured)

cfg = load_config(CONFIG_PATH)
if "joints" not in cfg:
    cfg = default_config()

# new_offset = old_offset + sign * captured_user_deg
# (so the captured pose decodes to 0 next time)
for name, user_deg in captured.items():
    if user_deg is None:
        print("calibrate: skipping", name, "(no read)")
        continue
    j = cfg["joints"][name]
    j["offset_deg"] = j["offset_deg"] + j["sign"] * user_deg

save_config(cfg, CONFIG_PATH)
print("Wrote", CONFIG_PATH)
