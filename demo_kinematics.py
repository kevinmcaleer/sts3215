"""Print the gripper-tip pose computed from the current joint positions."""
from sts3215 import STS3215
from buddy import Buddy
from kinematics import forward_kinematics, joint_angles_from_buddy


bus = STS3215(uart_id=0, tx_pin=0, rx_pin=1, baudrate=1_000_000)
buddy = Buddy(bus, config_path="/config.json")

angles = joint_angles_from_buddy(buddy)
print("Joint angles (deg):", angles)

x, y, z, roll, pitch, yaw = forward_kinematics(angles)
print("Gripper pose:")
print("  x = %.1f mm" % x)
print("  y = %.1f mm" % y)
print("  z = %.1f mm" % z)
print("  roll  = %.1f deg" % roll)
print("  pitch = %.1f deg" % pitch)
print("  yaw   = %.1f deg" % yaw)
