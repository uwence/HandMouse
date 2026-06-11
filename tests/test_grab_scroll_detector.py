from handmouse.grab_scroll_detector import (
    GrabScrollConfig,
    GrabScrollDetector,
    GrabScrollState,
)
from handmouse.types import FramePoint
from handmouse.tracking.observation import HandObservation, Point3


def make_config() -> GrabScrollConfig:
    return GrabScrollConfig(
        hold_ms=100,
        release_grace_ms=100,
        dead_zone=0.01,
        scroll_sensitivity=200.0,
        max_scroll_per_frame=12,
        thumb_index_max_distance=1.8,
        curled_finger_ratio=1.65,
        min_curled_fingers=2,
        post_release_grace_ms=120,
        only_active_when_draging=True,
    )


def make_detector() -> GrabScrollDetector:
    return GrabScrollDetector(make_config())


def grab_landmarks(y_offset: float = 0.0) -> list[Point3]:
    points = [Point3(0.0, 0.0, 0.0) for _ in range(21)]
    for index, point in {
        0: Point3(0.50, 0.80 + y_offset, 0.0),
        4: Point3(0.36, 0.55 + y_offset, 0.0),
        5: Point3(0.40, 0.56 + y_offset, 0.0),
        8: Point3(0.45, 0.50 + y_offset, 0.0),
        9: Point3(0.50, 0.52 + y_offset, 0.0),
        12: Point3(0.52, 0.49 + y_offset, 0.0),
        13: Point3(0.60, 0.56 + y_offset, 0.0),
        16: Point3(0.57, 0.52 + y_offset, 0.0),
        17: Point3(0.68, 0.62 + y_offset, 0.0),
        20: Point3(0.62, 0.58 + y_offset, 0.0),
    }.items():
        points[index] = point
    return points


def open_landmarks() -> list[Point3]:
    points = grab_landmarks()
    points[4] = Point3(0.20, 0.40, 0.0)
    points[8] = Point3(0.25, 0.10, 0.0)
    points[12] = Point3(0.45, 0.08, 0.0)
    points[16] = Point3(0.63, 0.12, 0.0)
    points[20] = Point3(0.78, 0.20, 0.0)
    return points

def make_obs(landmarks: list[Point3] | None) -> HandObservation | None:
    if landmarks is None:
        return None
    return HandObservation(
        frame_id=1,
        ts_ms=0,
        image_landmarks=landmarks,
        world_landmarks=landmarks,
        handedness_label="Left",
        handedness_score=0.9,
        raw_result=None,
        stale_ms=0,
        camera_space="mirrored"
    )

def test_initial_no_hand() -> None:
    detector = make_detector()

    result = detector.update(None, now_ms=0)

    assert detector._state == GrabScrollState.NO_HAND
    assert len(result) == 0


def test_grab_pose_enters_candidate() -> None:
    detector = make_detector()

    result = detector.update(make_obs(grab_landmarks()), now_ms=0)

    assert detector._state == GrabScrollState.CANDIDATE
    assert len(result) == 0


def test_hold_then_move_enters_dragging() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    result = detector.update(make_obs(grab_landmarks(y_offset=-0.08)), now_ms=140)

    assert detector._state == GrabScrollState.DRAGGING
    assert any(c.measurements.get("delta") == 12 for c in result)


def test_release_exits_to_released() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    detector.update(make_obs(grab_landmarks(y_offset=-0.08)), now_ms=140)

    result = detector.update(make_obs(open_landmarks()), now_ms=260)

    assert detector._state == GrabScrollState.RELEASED
    assert len(result) == 0


def test_static_grab_hold_does_not_emit_scroll() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    result = detector.update(make_obs(grab_landmarks()), now_ms=160)

    assert detector._state == GrabScrollState.GRABBING
    assert len(result) == 0


def test_active_only_true_when_dragging() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    hold = detector.update(make_obs(grab_landmarks()), now_ms=160)
    drag = detector.update(make_obs(grab_landmarks(y_offset=-0.08)), now_ms=200)

    assert detector._state == GrabScrollState.DRAGGING
    assert len(hold) == 0
    assert len(drag) == 1
    assert drag[0].measurements.get("delta") != 0


def test_release_grace_preserves_anchor_during_brief_loss() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    first_drag = detector.update(make_obs(grab_landmarks(y_offset=-0.08)), now_ms=140)
    missing = detector.update(None, now_ms=180)
    resumed = detector.update(make_obs(grab_landmarks(y_offset=-0.12)), now_ms=210)

    assert len(missing) == 0
    assert detector._state == GrabScrollState.DRAGGING
    assert len(resumed) == 1
    assert resumed[0].measurements.get("delta") != 0


def test_post_release_grace_smooths_re_grab() -> None:
    detector = make_detector()

    detector.update(make_obs(grab_landmarks()), now_ms=0)
    detector.update(make_obs(grab_landmarks()), now_ms=100)
    detector.update(make_obs(grab_landmarks(y_offset=-0.08)), now_ms=140)
    released = detector.update(make_obs(open_landmarks()), now_ms=260)
    regrab = detector.update(make_obs(grab_landmarks(y_offset=-0.12)), now_ms=310)

    assert detector._state == GrabScrollState.DRAGGING
    assert len(regrab) == 1
    assert regrab[0].measurements.get("delta") != 0
