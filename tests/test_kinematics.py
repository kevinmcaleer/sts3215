import math

import pytest

from kinematics import (
    JOINT_ORDER,
    L1, L2, L3, L4, L5,
    forward_kinematics,
    inverse_kinematics,
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


# --- inverse_kinematics ---------------------------------------------------


def _close(a, b, abs_tol=1e-3):
    return abs(a - b) < abs_tol


def _round_trip(target_pose, **kwargs):
    angles = inverse_kinematics(target_pose, **kwargs)
    assert angles is not None, "expected reachable pose"
    return forward_kinematics(angles)


def test_ik_home_pose_is_zero_angles():
    pose = (0.0, 0.0, L1 + L2 + L3 + L4 + L5, 0.0, 0.0, 0.0)
    angles = inverse_kinematics(pose)
    assert angles is not None
    for name in ("base", "shoulder", "elbow", "wrist_pitch", "wrist_roll"):
        assert _close(angles[name], 0.0, abs_tol=1e-6), name


def test_ik_round_trip_for_a_forward_reach():
    # Tilt arm forward (shoulder=90°, others 0) → tip is along +x axis.
    pose_in = (L2 + L3 + L4 + L5, 0.0, L1, 0.0, 90.0, 0.0)
    x_out, y_out, z_out, roll_out, pitch_out, yaw_out = _round_trip(pose_in)
    assert _close(x_out, pose_in[0], abs_tol=1e-3)
    assert _close(y_out, pose_in[1], abs_tol=1e-3)
    assert _close(z_out, pose_in[2], abs_tol=1e-3)


def test_ik_round_trip_for_a_pose_in_yz_plane():
    # Pose somewhere in the +y vertical plane.
    target_x = 0.0
    target_y = 150.0
    target_z = 200.0
    yaw = 90.0  # arm plane is +y
    pitch = 60.0
    pose_in = (target_x, target_y, target_z, 0.0, pitch, yaw)
    x_out, y_out, z_out, *_ = _round_trip(pose_in)
    assert _close(x_out, target_x, abs_tol=1e-3)
    assert _close(y_out, target_y, abs_tol=1e-3)
    assert _close(z_out, target_z, abs_tol=1e-3)


def test_ik_returns_none_for_too_far():
    # Tip way past the maximum reach.
    far = (L1 + L2 + L3 + L4 + L5) * 5
    angles = inverse_kinematics((far, 0.0, 0.0, 0.0, 0.0, 0.0))
    assert angles is None


def test_ik_returns_none_for_yaw_inconsistent_with_xy():
    # Target sits along +x (yaw should be 0) but caller asks for yaw=90°.
    pose = (200.0, 0.0, 100.0, 0.0, 60.0, 90.0)
    assert inverse_kinematics(pose) is None


def test_ik_yaw_consistent_within_tolerance_is_accepted():
    pose = (200.0, 0.0, 100.0, 0.0, 60.0, 0.5)
    angles = inverse_kinematics(pose, yaw_tolerance_deg=1.0)
    assert angles is not None


def test_ik_target_on_base_axis_accepts_any_yaw():
    # When (x, y) ≈ 0 the yaw is free; the caller gets to pick the base.
    pose = (0.0, 0.0, L1 + L2 + L3 + L4 + L5, 0.0, 0.0, 37.0)
    angles = inverse_kinematics(pose)
    assert angles is not None
    assert _close(angles["base"], 37.0, abs_tol=1e-6)


def test_ik_elbow_up_and_down_both_round_trip():
    # Pick a generic reachable pose and verify both branches reach it.
    pose_in = (120.0, 0.0, 180.0, 0.0, 30.0, 0.0)
    for elbow_up in (False, True):
        x_out, y_out, z_out, *_ = _round_trip(pose_in, elbow_up=elbow_up)
        assert _close(x_out, pose_in[0], abs_tol=1e-3)
        assert _close(y_out, pose_in[1], abs_tol=1e-3)
        assert _close(z_out, pose_in[2], abs_tol=1e-3)


def test_ik_elbow_up_and_down_pick_different_branches():
    pose_in = (120.0, 0.0, 180.0, 0.0, 30.0, 0.0)
    down = inverse_kinematics(pose_in, elbow_up=False)
    up = inverse_kinematics(pose_in, elbow_up=True)
    assert down["elbow"] != up["elbow"]
    assert _close(down["elbow"], -up["elbow"], abs_tol=1e-6)


def test_ik_propagates_wrist_roll_to_output_unchanged():
    pose = (200.0, 0.0, 80.0, 22.5, 90.0, 0.0)
    angles = inverse_kinematics(pose)
    assert angles is not None
    assert _close(angles["wrist_roll"], 22.5, abs_tol=1e-6)


def test_ik_unreachable_when_wrist_centre_too_close():
    # Force d < |L2 - L3| by aiming the wrist back into the shoulder.
    # Pick a position such that the wrist centre coincides with the shoulder.
    # Wrist centre = (rw, zw) = (-L4-L5*sin(phi)+r, ...). With pitch=180°
    # (gripper pointing down) and r=0, z=L1, the wrist centre lands at
    # (0, L1 + (L4+L5)) — within reach. Instead, use d_sq small via short z.
    # Simplest: ask for tip exactly at the shoulder, pitch 0 → wrist centre
    # at (0, L1 - (L4+L5)), i.e. d = L4+L5 below the shoulder.
    if (L4 + L5) < abs(L2 - L3):
        pose = (0.0, 0.0, L1 - (L4 + L5), 0.0, 0.0, 0.0)
        assert inverse_kinematics(pose) is None
    else:
        pytest.skip("link lengths don't trigger the inner-bound branch")
