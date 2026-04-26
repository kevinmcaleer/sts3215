"""Forward kinematics for the Buddy 6-DOF arm.

Pure Python (MicroPython compatible) — uses only the `math` module. No numpy.

Convention
----------
- Right-handed coordinates with +z up.
- Home pose (every joint at 0 deg) is the arm extended straight up; the
  gripper tip sits at (0, 0, L1+L2+L3+L4+L5) in the base frame.
- Joint axes (in the body frame at the home pose):
    base         — rotation about world z (yaw)
    shoulder     — rotation about y (tilts the upper arm forward)
    elbow        — rotation about y (bends the forearm)
    wrist_pitch  — rotation about y (tilts the wrist)
    wrist_roll   — rotation about z (twists the end-effector)
    gripper      — open / close; not part of the kinematic chain.

Link lengths are module-level constants in millimetres so they can be
tuned to match the physical arm.
"""
import math

# Link lengths in millimetres. Placeholder values — tune for your build.
L1 = 60.0    # base column (base servo to shoulder pivot)
L2 = 110.0   # upper arm (shoulder to elbow)
L3 = 110.0   # forearm (elbow to wrist pitch)
L4 = 40.0    # wrist (wrist pitch to wrist roll)
L5 = 70.0    # gripper / tool (wrist roll to fingertip)

JOINT_ORDER = ["base", "shoulder", "elbow",
               "wrist_pitch", "wrist_roll", "gripper"]


def _identity():
    return [[1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _matmul(A, B):
    C = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        ai0, ai1, ai2, ai3 = A[i]
        for j in range(4):
            C[i][j] = (ai0 * B[0][j] + ai1 * B[1][j]
                       + ai2 * B[2][j] + ai3 * B[3][j])
    return C


def _rot_z(theta):
    c, s = math.cos(theta), math.sin(theta)
    return [[c, -s, 0.0, 0.0],
            [s,  c, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _rot_y(theta):
    c, s = math.cos(theta), math.sin(theta)
    return [[c,  0.0, s,  0.0],
            [0.0, 1.0, 0.0, 0.0],
            [-s, 0.0, c,  0.0],
            [0.0, 0.0, 0.0, 1.0]]


def _trans_z(d):
    return [[1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, d],
            [0.0, 0.0, 0.0, 1.0]]


def forward_kinematics(joint_angles_deg):
    """Compute the gripper-tip pose for the given joint angles.

    Args:
        joint_angles_deg: dict keyed by joint name (every name in
            JOINT_ORDER is required). Values are user-frame degrees, as
            reported by Buddy.read_all_positions (joint offsets already
            subtracted). The gripper angle is read but does not affect
            tip position or orientation.

    Returns:
        Tuple (x, y, z, roll_deg, pitch_deg, yaw_deg) in millimetres and
        degrees, expressed in the base frame. Orientation is ZYX
        intrinsic Euler (yaw → pitch → roll).
    """
    missing = [n for n in JOINT_ORDER if n not in joint_angles_deg]
    if missing:
        raise KeyError("missing joint angle(s): " + ", ".join(missing))

    th_base = math.radians(joint_angles_deg["base"])
    th_sh = math.radians(joint_angles_deg["shoulder"])
    th_el = math.radians(joint_angles_deg["elbow"])
    th_wp = math.radians(joint_angles_deg["wrist_pitch"])
    th_wr = math.radians(joint_angles_deg["wrist_roll"])

    T = _identity()
    T = _matmul(T, _rot_z(th_base))
    T = _matmul(T, _trans_z(L1))
    T = _matmul(T, _rot_y(th_sh))
    T = _matmul(T, _trans_z(L2))
    T = _matmul(T, _rot_y(th_el))
    T = _matmul(T, _trans_z(L3))
    T = _matmul(T, _rot_y(th_wp))
    T = _matmul(T, _trans_z(L4))
    T = _matmul(T, _rot_z(th_wr))
    T = _matmul(T, _trans_z(L5))

    x, y, z = T[0][3], T[1][3], T[2][3]

    # ZYX intrinsic Euler extraction (yaw → pitch → roll).
    sy = math.sqrt(T[0][0] * T[0][0] + T[1][0] * T[1][0])
    if sy > 1e-6:
        yaw = math.atan2(T[1][0], T[0][0])
        pitch = math.atan2(-T[2][0], sy)
        roll = math.atan2(T[2][1], T[2][2])
    else:
        # Gimbal lock: pitch ≈ ±90°. Pin yaw and absorb the rotation in roll.
        yaw = 0.0
        pitch = math.atan2(-T[2][0], sy)
        roll = math.atan2(-T[1][2], T[1][1])

    return (x, y, z,
            math.degrees(roll),
            math.degrees(pitch),
            math.degrees(yaw))


def joint_angles_from_buddy(buddy):
    """Read current joint angles from a Buddy as a dict ready for FK.

    Joints whose position is unreadable (bus returned None) default to 0.
    """
    positions = buddy.read_all_positions()
    return {name: (positions.get(name) if positions.get(name) is not None
                   else 0.0)
            for name in JOINT_ORDER}
