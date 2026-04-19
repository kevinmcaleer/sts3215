"""
Mini demo for the "Why are Bus Servos better?" video.

Two STS3215 servos daisy-chained on a single bus (IDs 1 and 2).
Servo 1 sweeps back and forth, servo 2 follows with a short delay,
producing a wave-like motion. Live position feedback is printed
to the terminal for both servos.
"""

import math
import time

from sts3215 import STS3215, position_to_degrees

SERVO_1 = 1
SERVO_2 = 2

CENTRE = 2048
AMPLITUDE = 1000   # ~±88 degrees around centre
STEPS = 60         # samples per full sweep cycle
STEP_DELAY_MS = 40
FOLLOW_LAG = 6     # servo 2 trails servo 1 by this many steps
SPEED = 2400
ACC = 50


def sweep_positions(steps, centre, amplitude):
    """Yield a smooth back-and-forth sweep using a sine wave."""
    for i in range(steps):
        yield int(centre + amplitude * math.sin(2 * math.pi * i / steps))


def main():
    bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)

    for sid in (SERVO_1, SERVO_2):
        bus.set_torque(sid, True)

    # Park both servos at centre before the sweep.
    bus.move(SERVO_1, CENTRE, speed=SPEED, acc=ACC)
    bus.move(SERVO_2, CENTRE, speed=SPEED, acc=ACC)
    time.sleep_ms(500)

    targets = list(sweep_positions(STEPS, CENTRE, AMPLITUDE))

    print("Starting wave demo. Ctrl-C to stop.")
    try:
        i = 0
        while True:
            t1 = targets[i % STEPS]
            t2 = targets[(i - FOLLOW_LAG) % STEPS]

            bus.move(SERVO_1, t1, speed=SPEED, acc=ACC)
            bus.move(SERVO_2, t2, speed=SPEED, acc=ACC)

            p1 = bus.read_position(SERVO_1)
            p2 = bus.read_position(SERVO_2)

            print("step {:3d}  s1 target={:4d} pos={}  s2 target={:4d} pos={}".format(
                i,
                t1, _fmt_pos(p1),
                t2, _fmt_pos(p2),
            ))

            time.sleep_ms(STEP_DELAY_MS)
            i += 1
    except KeyboardInterrupt:
        print("\nStopping. Releasing torque.")
        bus.move(SERVO_1, CENTRE, speed=SPEED, acc=ACC)
        bus.move(SERVO_2, CENTRE, speed=SPEED, acc=ACC)
        time.sleep_ms(500)
        bus.set_torque(SERVO_1, False)
        bus.set_torque(SERVO_2, False)


def _fmt_pos(pos):
    if pos is None:
        return "----  (---.-)"
    return "{:4d}  ({:5.1f})".format(pos, position_to_degrees(pos))


if __name__ == "__main__":
    main()
