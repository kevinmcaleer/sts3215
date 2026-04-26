from sts3215 import STS3215, degrees_to_position, position_to_degrees


DEFAULT_JOINTS = {
    "base":        {"id": 1, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
    "shoulder":    {"id": 2, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
    "elbow":       {"id": 3, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
    "wrist_pitch": {"id": 4, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
    "wrist_roll":  {"id": 5, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
    "gripper":     {"id": 6, "min_deg": 0, "max_deg": 360, "offset_deg": 0, "sign":  1},
}


class Buddy:
    """Six-joint arm wrapper around the STS3215 bus driver."""

    def __init__(self, bus, joints=None):
        self.bus = bus
        self.joints = joints if joints is not None else DEFAULT_JOINTS

    def _joint(self, name):
        if name not in self.joints:
            raise KeyError("unknown joint: " + name)
        return self.joints[name]

    def _user_to_raw(self, joint, user_deg):
        return degrees_to_position(joint["offset_deg"] + joint["sign"] * user_deg)

    def _raw_to_user(self, joint, raw):
        return (position_to_degrees(raw) - joint["offset_deg"]) / joint["sign"]

    def ping_all(self):
        return {name: self.bus.ping(j["id"]) for name, j in self.joints.items()}

    def read_all_positions(self):
        result = {}
        for name, j in self.joints.items():
            raw = self.bus.read_position(j["id"])
            result[name] = self._raw_to_user(j, raw) if raw is not None else None
        return result

    def move_joint(self, name, degrees, speed=0, acc=50):
        joint = self._joint(name)
        clamped = max(joint["min_deg"], min(joint["max_deg"], degrees))
        if clamped != degrees:
            print("buddy: clamped", name, degrees, "->", clamped)
        self.bus.move(joint["id"], self._user_to_raw(joint, clamped),
                      speed=speed, acc=acc)

    def move_all(self, targets, speed=0, acc=50):
        for name, degrees in targets.items():
            self.move_joint(name, degrees, speed=speed, acc=acc)

    def set_torque_all(self, enable):
        for j in self.joints.values():
            self.bus.set_torque(j["id"], enable)

    def gripper_open(self, speed=0, acc=50):
        joint = self._joint("gripper")
        self.move_joint("gripper", joint["max_deg"], speed=speed, acc=acc)

    def gripper_close(self, speed=0, acc=50):
        joint = self._joint("gripper")
        self.move_joint("gripper", joint["min_deg"], speed=speed, acc=acc)
