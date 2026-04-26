# Buddy - Epic Documentation

## Overview

Buddy is a MicroPython powered robot arm, based on the STS3215 bus servo motors. It is designed to be an affordable and accessible platform for learning robotics and programming. The robot arm can be controlled using a variety of interfaces, including a web-based dashboard, a mobile app, and a command-line interface.

---

## Features

### Core movement
- each of the 6 motors can be controlled independently, allowing for a wide range of motion and precision in tasks.
- motors can be given a specfic target position, and the arm will move to that position using a PID controller to ensure smooth and accurate movement.
- the arm can also be controlled using inverse kinematics, allowing for more complex movements and tasks.
- the web interface runs from the microcontroller itself, allowing for easy access and control from any device with a web browser
- the web interface includes a 3d visualization of the arm, allowing users to see the current position and movement of the arm in real-time.
- the web interface also includes controls for moving the arm, as well as a command-line interface for more advanced users.
- the arm also has sliders for each of the 6 motors, allowing for manual control and fine-tuning of the arm's movements. These sliders can be used in conjunction with the web interface or independently for more direct control.

The 3d model allows the gripper to be positioned using inverse kinematics, which calculates the necessary joint angles to achieve a desired position and orientation of the gripper. This allows for more intuitive control of the arm, as users can simply specify where they want the gripper to be, rather than having to manually adjust each joint.

The interface is mostly Javascript, with micropython backend running on the microcontroller. The backend handles the communication with the motors and sensors, while the frontend provides a user-friendly interface for controlling the arm and visualizing its movements.

### Additional features
- the arm includes a gripper that can be opened and closed to pick up and manipulate objects
- motors torque can be enabled and disabled, allowing for manual manipulation of the arm when torque is disabled

