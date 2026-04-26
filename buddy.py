import time

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

    def __init__(self, bus, joints=None, config_path=None):
        self.bus = bus
        if joints is not None:
            self.joints = joints
        elif config_path is not None:
            from config import load_config
            self.joints = load_config(config_path)["joints"]
        else:
            self.joints = DEFAULT_JOINTS
        # Last value passed to set_torque_all — exposed for status readouts.
        # None means the state hasn't been set this session.
        self.torque_enabled = None

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

    def move_all_sync(self, targets, duration_ms=None, max_speed=None,
                      acc=50, wait=False, poll_interval_ms=50, timeout_ms=10000):
        """Move several joints so they arrive at their targets together.

        Pass exactly one of:
          duration_ms — every joint should take this long; per-joint speed is
            scaled by its travel distance (delta / duration).
          max_speed — speed for the longest-travel joint; shorter-travel joints
            are scaled down so they finish at the same time.

        If wait is True, poll read_moving on each joint until it reports
        stopped or timeout_ms elapses.
        """
        if (duration_ms is None) == (max_speed is None):
            raise ValueError("specify exactly one of duration_ms or max_speed")
        if duration_ms is not None and duration_ms <= 0:
            raise ValueError("duration_ms must be positive")
        if max_speed is not None and max_speed <= 0:
            raise ValueError("max_speed must be positive")

        plan = []
        for name, degrees in targets.items():
            joint = self._joint(name)
            clamped = max(joint["min_deg"], min(joint["max_deg"], degrees))
            if clamped != degrees:
                print("buddy: clamped", name, degrees, "->", clamped)
            target_raw = self._user_to_raw(joint, clamped)
            current_raw = self.bus.read_position(joint["id"])
            if current_raw is None:
                print("buddy: skip", name, "(no position)")
                continue
            delta = abs(target_raw - current_raw)
            plan.append((name, joint, target_raw, delta))

        if not plan:
            return

        if duration_ms is not None:
            seconds = duration_ms / 1000.0
            speeds = [max(1, int(delta / seconds)) for _, _, _, delta in plan]
        else:
            max_delta = max(delta for _, _, _, delta in plan) or 1
            speeds = [max(1, int(max_speed * delta / max_delta))
                      for _, _, _, delta in plan]

        moving_ids = []
        for (_, joint, target_raw, delta), speed in zip(plan, speeds):
            self.bus.move(joint["id"], target_raw, speed=speed, acc=acc)
            if delta > 0:
                moving_ids.append(joint["id"])

        if wait and moving_ids:
            self._wait_for_stop(moving_ids, poll_interval_ms, timeout_ms)

    def _wait_for_stop(self, ids, poll_interval_ms, timeout_ms):
        deadline = time.ticks_add(time.ticks_ms(), timeout_ms)
        pending = list(ids)
        while pending and time.ticks_diff(deadline, time.ticks_ms()) > 0:
            still = []
            for sid in pending:
                state = self.bus.read_moving(sid)
                if state:
                    still.append(sid)
            pending = still
            if pending:
                time.sleep_ms(poll_interval_ms)

    def set_torque_all(self, enable):
        for j in self.joints.values():
            self.bus.set_torque(j["id"], enable)
        self.torque_enabled = bool(enable)

    def gripper_open(self, speed=0, acc=50):
        joint = self._joint("gripper")
        self.move_joint("gripper", joint["max_deg"], speed=speed, acc=acc)

    def gripper_close(self, speed=0, acc=50):
        joint = self._joint("gripper")
        self.move_joint("gripper", joint["min_deg"], speed=speed, acc=acc)

    def move_to_pose(self, x, y, z, roll=0.0, pitch=0.0, yaw=None,
                     duration_ms=None, max_speed=None, acc=50,
                     wait=False, elbow_up=False):
        """Solve IK for the target pose and move all joints together.

        If yaw is omitted, the base rotation is taken from atan2(y, x).
        Raises ValueError if the pose is outside the workspace.
        """
        from kinematics import inverse_kinematics
        import math as _math

        if yaw is None:
            yaw = _math.degrees(_math.atan2(y, x))
        angles = inverse_kinematics((x, y, z, roll, pitch, yaw),
                                    elbow_up=elbow_up)
        if angles is None:
            raise ValueError("pose unreachable: ({}, {}, {})".format(x, y, z))

        # The IK result includes a gripper entry; the pose doesn't constrain
        # the gripper, so leave that joint alone. Also skip any joint not
        # present in this Buddy's config.
        targets = {n: a for n, a in angles.items()
                   if n != "gripper" and n in self.joints}
        if duration_ms is None and max_speed is None:
            max_speed = 600
        self.move_all_sync(targets, duration_ms=duration_ms,
                           max_speed=max_speed, acc=acc, wait=wait)
        return targets
