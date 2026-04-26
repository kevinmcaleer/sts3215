import time

from sts3215 import STS3215
from buddy import Buddy


bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy = Buddy(bus, config_path="/config.json")

print("Ping:", buddy.ping_all())
time.sleep_ms(200)

print("Positions:", buddy.read_all_positions())
time.sleep_ms(200)

buddy.set_torque_all(True)
time.sleep_ms(200)

buddy.move_joint("elbow", 185, speed=600, acc=20)
time.sleep_ms(800)
buddy.move_joint("elbow", 175, speed=600, acc=20)
time.sleep_ms(800)

buddy.move_all({"shoulder": 185, "wrist_pitch": 175}, speed=600, acc=20)
time.sleep_ms(1000)
buddy.move_all({"shoulder": 175, "wrist_pitch": 185}, speed=600, acc=20)
time.sleep_ms(1000)

buddy.gripper_open(speed=600, acc=20)
time.sleep_ms(800)
buddy.gripper_close(speed=600, acc=20)
time.sleep_ms(800)

# Release torque so the arm can be repositioned by hand.
buddy.set_torque_all(False)
print("Torque off — arm is free to move by hand.")
