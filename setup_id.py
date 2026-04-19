from sts3215 import STS3215
from time import sleep_ms

servo = STS3215(uart_id=0, tx_pin=0, rx_pin=1)

print(servo.ping(1))
      
# servo.set_id(current_id=4, new_id=1)

print(f"servo 1: {servo.ping(1)}")
print(f"servo 2: {servo.ping(2)}")
print(f"servo 3: {servo.ping(3)}")
print(f"servo 4: {servo.ping(4)}")

