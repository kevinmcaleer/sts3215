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


# --- Inverse kinematics ---------------------------------------------------


def inverse_kinematics(target_pose, elbow_up=False, yaw_tolerance_deg=1.0):
    """Solve for joint angles that achieve the target pose.

    The arm has 5 effective rotational DOF (base + 3 pitch + wrist_roll), so
    the arm always lies in the vertical plane containing the base axis and
    the target. The pose is interpreted intrinsically:
      - yaw    → base rotation; must be consistent with atan2(y, x).
      - pitch  → approach pitch in the arm plane (sum of shoulder + elbow +
                 wrist_pitch).
      - roll   → wrist_roll twist about the approach axis.

    Args:
        target_pose: (x, y, z, roll_deg, pitch_deg, yaw_deg) in mm / degrees.
        elbow_up: pick the elbow-up branch of the 2-link IK (else elbow-down).
        yaw_tolerance_deg: how far the requested yaw may sit from
            atan2(y, x) before the pose is rejected. The check is skipped
            when the target is on the base axis (xy ≈ 0).

    Returns:
        dict of joint angles in degrees keyed by JOINT_ORDER (gripper = 0),
        or None if the pose is outside the workspace or yaw is inconsistent.
    """
    x, y, z, roll_deg, pitch_deg, yaw_deg = target_pose

    # Base rotation: arm plane must contain the target.
    on_axis = math.sqrt(x * x + y * y) < 1e-6
    if on_axis:
        base_deg = yaw_deg
    else:
        base_deg = math.degrees(math.atan2(y, x))
        delta = ((yaw_deg - base_deg + 180.0) % 360.0) - 180.0
        if abs(delta) > yaw_tolerance_deg:
            return None

    # Project the target into the arm's vertical (r, z) plane.
    r = math.sqrt(x * x + y * y)
    phi = math.radians(pitch_deg)

    # Wrist-pitch axis sits (L4 + L5) back along the approach direction.
    rw = r - (L4 + L5) * math.sin(phi)
    zw = z - (L4 + L5) * math.cos(phi)

    # Two-link planar IK from the shoulder pivot at (0, L1) to the wrist
    # centre (rw, zw).
    dr = rw
    dz = zw - L1
    d_sq = dr * dr + dz * dz
    d = math.sqrt(d_sq)
    if d > L2 + L3 or d < abs(L2 - L3):
        return None

    cos_e = (d_sq - L2 * L2 - L3 * L3) / (2.0 * L2 * L3)
    cos_e = max(-1.0, min(1.0, cos_e))
    theta_e = math.acos(cos_e)
    if elbow_up:
        theta_e = -theta_e

    alpha = math.atan2(dr, dz)
    beta = math.atan2(L3 * math.sin(theta_e), L2 + L3 * math.cos(theta_e))
    theta_s = alpha - beta

    theta_wp = phi - theta_s - theta_e

    return {
        "base":        base_deg,
        "shoulder":    math.degrees(theta_s),
        "elbow":       math.degrees(theta_e),
        "wrist_pitch": math.degrees(theta_wp),
        "wrist_roll":  roll_deg,
        "gripper":     0.0,
    }
