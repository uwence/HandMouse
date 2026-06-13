from handmouse.tracking.observation import HandObservation, Point3
from handmouse.tracking.palm_orientation import (
    DEFAULT_NORMAL_Z_MIN,
    compute_palm_orientation,
)


def _obs(world_landmarks: list[Point3] | None) -> HandObservation:
    lm = [Point3(0.5, 0.5, 0.0)] * 21
    return HandObservation(
        frame_id=1, ts_ms=0, image_landmarks=lm, world_landmarks=world_landmarks,
        handedness_label="Left", handedness_score=0.9,
        raw_result=None, stale_ms=0, camera_space="mirrored",
    )


def _world_palm_facing_camera() -> list[Point3]:
    # Palm in XY plane: wrist at origin, index_mcp +x, pinky_mcp -x and +y.
    # Normal = (index-wrist) X (pinky-wrist) along Z.
    world = [Point3(0.0, 0.0, 0.0)] * 21
    world[5] = Point3(0.08, -0.02, 0.0)
    world[17] = Point3(-0.05, -0.02, 0.0)
    return world


def _world_palm_sideways() -> list[Point3]:
    # Palm in XZ plane (edge-on to camera): normal lies in Y, nz ~= 0.
    world = [Point3(0.0, 0.0, 0.0)] * 21
    world[5] = Point3(0.08, 0.0, 0.0)
    world[17] = Point3(0.0, 0.0, 0.08)
    return world


def test_returns_none_without_world_landmarks():
    assert compute_palm_orientation(_obs(None)) is None


def test_returns_none_without_obs():
    assert compute_palm_orientation(None) is None


def test_palm_facing_camera_is_valid():
    ori = compute_palm_orientation(_obs(_world_palm_facing_camera()))
    assert ori is not None
    assert ori.is_valid is True
    assert abs(ori.normal_z) >= DEFAULT_NORMAL_Z_MIN


def test_sideways_palm_is_invalid():
    ori = compute_palm_orientation(_obs(_world_palm_sideways()))
    assert ori is not None
    assert ori.is_valid is False
    assert abs(ori.normal_z) < DEFAULT_NORMAL_Z_MIN


def test_threshold_override_can_pass_sideways():
    ori = compute_palm_orientation(_obs(_world_palm_sideways()), normal_z_min=0.0)
    assert ori is not None
    assert ori.is_valid is True


def test_degenerate_world_landmarks_invalid():
    world = [Point3(0.0, 0.0, 0.0)] * 21  # collinear/zero vectors
    ori = compute_palm_orientation(_obs(world))
    assert ori is not None
    assert ori.is_valid is False
    assert ori.normal_z == 0.0
