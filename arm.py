import math
import time

from sts3215 import STS3215, position_to_degrees

CLAW = 1
WRIST = 2
ARM = 3
ELBOW = 4

CENTRE = 2048
STEPS = 60         # samples per full sweep cycle
SPEED = 2400
ACC = 50
CLAW_MIN = 0
CLAW_MAX = 2048

bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)

# Set Torque (apply power)
# for sid in (CLAW, WRIST, ARM, ELBOW):
#     bus.set_torque(sid, True)

claw_pos = 0
wrist_pos = 0

SERVOS = [CLAW, WRIST, ARM, ELBOW]
for servo in SERVOS:
    print(f"Pinging {servo} {bus.ping(servo)}")
    time.sleep_ms(500)

while True:
    claw_pos = bus.read_position(CLAW)
    time.sleep_ms(500)
    wrist_pos = bus.read_position(WRIST)
    time.sleep_ms(500)
    
    print(f"Claw Pos: {claw_pos}, Wrist Pos: {wrist_pos}")
    time.sleep_ms(500)
  
# bus.move(SERVO_1, CENTRE, speed=SPEED, acc=ACC)
# bus.move(SERVO_2, CENTRE, speed=SPEED, acc=ACC)



