"""Drive the arm to a sequence of Cartesian poses via IK."""
import time

from sts3215 import STS3215
from buddy import Buddy
from kinematics import L1, L2, L3, L4, L5


bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy = Buddy(bus, config_path="/config.json")

print("Ping:", buddy.ping_all())
buddy.set_torque_all(True)
time.sleep_ms(200)

REACH = L2 + L3
HOME_Z = L1 + L2 + L3 + L4 + L5

poses = [
    # (x_mm, y_mm, z_mm, roll, pitch, yaw)
    (0.0,        0.0, HOME_Z, 0.0, 0.0,  0.0),  # straight up
    (REACH,      0.0, L1,     0.0, 90.0, 0.0),  # forward, horizontal
    (0.0,        REACH, L1,   0.0, 90.0, 90.0), # left, horizontal
    (REACH * 0.6, 0.0, L1 + 100, 0.0, 45.0, 0.0),  # forward & up
    (0.0,        0.0, HOME_Z, 0.0, 0.0,  0.0),  # back home
]

for x, y, z, r, p, yaw in poses:
    print("Move to (%.0f, %.0f, %.0f) pitch=%.0f yaw=%.0f"
          % (x, y, z, p, yaw))
    try:
        buddy.move_to_pose(x, y, z, roll=r, pitch=p, yaw=yaw,
                           duration_ms=1500, acc=20, wait=True)
    except ValueError as e:
        print("  unreachable:", e)
    time.sleep_ms(300)

buddy.set_torque_all(False)
print("Done — torque off.")
