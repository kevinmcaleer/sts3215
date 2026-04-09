from sts3215 import STS3215
from time import sleep

servo = STS3215(uart_id=0, tx_pin=0, rx_pin=1)

# Change the servo currently at ID 1 to ID 3

id = 2

servo.set_id(1, id)
print("Done. Power cycle the servo, then verify:")
sleep(1)

# Verify the new ID works
print("verifying...")
if servo.ping(id):
    print(f"Servo responds at new ID {id}")
else:
    for n in range(1, 10):
      print(f"checking servo {n}:")
      if servo.ping(n):
        print(f"Servo responds at  ID {n}")