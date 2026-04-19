from sts3215 import STS3215
from time import sleep_ms

servo = STS3215(uart_id=0, tx_pin=0, rx_pin=1)

SCS_ID = 1
SCS_MINIMUM_POSITION_VALUE = 0
SCS_MAXIMUM_POSITION_VALUE = 4095
SCS_MOVING_SPEED = 2400
SCS_MOVING_ACC = 50 

goal_positions = [SCS_MINIMUM_POSITION_VALUE, SCS_MAXIMUM_POSITION_VALUE]
index = 0

# Print out model number
print("Model number:", servo.read_model(1))      


# Check servo is responding
print("Pinging servo ID %d..." % SCS_ID)
if servo.ping(SCS_ID):
    print("Servo ID %d found" % SCS_ID)
else:
    print("ERROR: No response from servo ID %d" % SCS_ID)

print("Starting move loop...")

while True:
    goal = goal_positions[index]
    print("\n--- Moving to position %d ---" % goal)

    # Send move command
    servo.move(SCS_ID, goal, speed=SCS_MOVING_SPEED, acc=SCS_MOVING_ACC)
    print("Move command sent (pos=%d, speed=%d, acc=%d)" % (goal, SCS_MOVING_SPEED, SCS_MOVING_ACC))

    # Poll position/speed until movement completes
    poll_count = 0
    while True:
        position, speed = servo.read_pos_speed(SCS_ID)
        moving = servo.read_moving(SCS_ID)
        print("  poll %d: pos=%s spd=%s moving=%s" % (poll_count, position, speed, moving))
        poll_count += 1

        if moving == 0 or moving is None:
            if moving is None:
                print("  WARNING: read_moving returned None (no response)")
            else:
                print("  Movement complete")
            break
        sleep_ms(100)

    # Toggle goal position
    index = 1 - index
    sleep_ms(1000)
