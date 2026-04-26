from sts3215 import STS3215
from time import sleep_ms, sleep

servo = STS3215(uart_id=0, tx_pin=0, rx_pin=1)
      
target_id = 2
current_id = 4     
      
print(f"servo on {current_id}: {servo.ping(1)}")   
servo.set_id(current_id=current_id, new_id=target_id)

print(f"servo on {target_id}: {servo.ping(target_id)}")
print(f"servo on {current_id}: {servo.ping(current_id)}")



