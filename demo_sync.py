import time

from sts3215 import STS3215
from buddy import Buddy


HOME = {
    "base": 180,
    "shoulder": 180,
    "elbow": 180,
    "wrist_pitch": 180,
    "wrist_roll": 180,
}

REACH = {
    "base": 220,
    "shoulder": 150,
    "elbow": 210,
    "wrist_pitch": 165,
    "wrist_roll": 200,
}


bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy = Buddy(bus, config_path="/config.json")

print("Ping:", buddy.ping_all())
buddy.set_torque_all(True)
time.sleep_ms(200)

print("Move HOME (synchronised, 1500 ms)")
buddy.move_all_sync(HOME, duration_ms=1500, acc=20, wait=True)

print("Move REACH (synchronised, 1500 ms)")
buddy.move_all_sync(REACH, duration_ms=1500, acc=20, wait=True)

print("Move HOME again, paced by max_speed=600")
buddy.move_all_sync(HOME, max_speed=600, acc=20, wait=True)

buddy.set_torque_all(False)
print("Done — torque off.")
