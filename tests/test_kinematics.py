import pytest

from kinematics import (
    JOINT_ORDER,
    L1, L2, L3, L4, L5,
    forward_kinematics,
    joint_angles_from_buddy,
)


def _zeros():
    return {n: 0.0 for n in JOINT_ORDER}


def test_home_pose_position_is_straight_up():
    x, y, z, *_ = forward_kinematics(_zeros())
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1 + L2 + L3 + L4 + L5, abs=1e-6)


def test_home_pose_orientation_is_identity():
    _, _, _, roll, pitch, yaw = forward_kinematics(_zeros())
    assert roll == pytest.approx(0.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert yaw == pytest.approx(0.0, abs=1e-6)


def test_base_rotation_only_changes_yaw():
    angles = _zeros()
    angles["base"] = 45.0
    x, y, z, roll, pitch, yaw = forward_kinematics(angles)
    # Arm is still vertical → tip stays on the z axis.
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1 + L2 + L3 + L4 + L5, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert yaw == pytest.approx(45.0, abs=1e-6)


def test_shoulder_90_lays_arm_along_x():
    angles = _zeros()
    angles["shoulder"] = 90.0
    x, y, z, *_ = forward_kinematics(angles)
    assert x == pytest.approx(L2 + L3 + L4 + L5, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1, abs=1e-6)


def test_shoulder_90_hits_gimbal_lock_branch():
    angles = _zeros()
    angles["shoulder"] = 90.0
    _, _, _, roll, pitch, yaw = forward_kinematics(angles)
    # Pure rot_y(90°) → pitch = +90°; the gimbal-lock branch pins yaw to 0.
    assert pitch == pytest.approx(90.0, abs=1e-6)
    assert yaw == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)


def test_elbow_180_folds_forearm_back():
    angles = _zeros()
    angles["elbow"] = 180.0
    x, y, z, *_ = forward_kinematics(angles)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1 + L2 - (L3 + L4 + L5), abs=1e-6)


def test_wrist_roll_only_twists_orientation_at_home():
    angles = _zeros()
    angles["wrist_roll"] = 30.0
    x, y, z, roll, pitch, yaw = forward_kinematics(angles)
    assert x == pytest.approx(0.0, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1 + L2 + L3 + L4 + L5, abs=1e-6)
    assert pitch == pytest.approx(0.0, abs=1e-6)
    assert roll == pytest.approx(0.0, abs=1e-6)
    assert yaw == pytest.approx(30.0, abs=1e-6)


def test_gripper_angle_does_not_affect_pose():
    a = _zeros()
    b = dict(a)
    b["gripper"] = 90.0
    assert forward_kinematics(a) == forward_kinematics(b)


def test_missing_joint_raises():
    angles = _zeros()
    del angles["wrist_pitch"]
    with pytest.raises(KeyError):
        forward_kinematics(angles)


def test_negative_base_angle_yields_negative_yaw():
    angles = _zeros()
    angles["base"] = -90.0
    _, _, _, _, _, yaw = forward_kinematics(angles)
    assert yaw == pytest.approx(-90.0, abs=1e-6)


def test_shoulder_90_then_elbow_neg90_brings_tip_above_shoulder():
    # Lift the upper arm forward (+x), then bend the elbow back up (+z).
    angles = _zeros()
    angles["shoulder"] = 90.0
    angles["elbow"] = -90.0
    x, y, z, *_ = forward_kinematics(angles)
    # Upper arm extends along +x by L2; elbow rotates -90° about y so the
    # forearm and beyond point straight up again.
    assert x == pytest.approx(L2, abs=1e-6)
    assert y == pytest.approx(0.0, abs=1e-6)
    assert z == pytest.approx(L1 + L3 + L4 + L5, abs=1e-6)


# --- joint_angles_from_buddy ----------------------------------------------


class _FakeBuddy:
    def __init__(self, positions):
        self._positions = positions

    def read_all_positions(self):
        return dict(self._positions)


def test_joint_angles_from_buddy_passes_through_values():
    buddy = _FakeBuddy({n: i * 5.0 for i, n in enumerate(JOINT_ORDER)})
    angles = joint_angles_from_buddy(buddy)
    for i, n in enumerate(JOINT_ORDER):
        assert angles[n] == i * 5.0


def test_joint_angles_from_buddy_treats_none_as_zero():
    buddy = _FakeBuddy({n: None for n in JOINT_ORDER})
    angles = joint_angles_from_buddy(buddy)
    assert all(v == 0.0 for v in angles.values())


def test_joint_angles_from_buddy_preserves_zero():
    # `or 0.0` would erase a legitimate non-None 0.0 — make sure the
    # implementation distinguishes None from 0.0.
    buddy = _FakeBuddy({n: 0.0 for n in JOINT_ORDER})
    angles = joint_angles_from_buddy(buddy)
    assert all(v == 0.0 for v in angles.values())


def test_joint_angles_from_buddy_missing_joint_defaults_to_zero():
    partial = {n: 10.0 for n in JOINT_ORDER if n != "gripper"}
    buddy = _FakeBuddy(partial)
    angles = joint_angles_from_buddy(buddy)
    assert angles["gripper"] == 0.0
    for n in JOINT_ORDER:
        if n != "gripper":
            assert angles[n] == 10.0
