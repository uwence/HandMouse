from handmouse.config import GrabScrollConfig
from handmouse.grab_scroll_detector import GrabScrollDetector, GrabScrollState
from handmouse.pointer_mapper import FramePoint


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
    )


def make_detector() -> GrabScrollDetector:
    return GrabScrollDetector(make_config())


def grab_landmarks(y_offset: float = 0.0) -> list[FramePoint]:
    points = [FramePoint(0.0, 0.0) for _ in range(21)]
    for index, point in {
        0: FramePoint(0.50, 0.80 + y_offset),
        4: FramePoint(0.36, 0.55 + y_offset),
        5: FramePoint(0.40, 0.56 + y_offset),
        8: FramePoint(0.45, 0.50 + y_offset),
        9: FramePoint(0.50, 0.52 + y_offset),
        12: FramePoint(0.52, 0.49 + y_offset),
        13: FramePoint(0.60, 0.56 + y_offset),
        16: FramePoint(0.57, 0.52 + y_offset),
        17: FramePoint(0.68, 0.62 + y_offset),
        20: FramePoint(0.62, 0.58 + y_offset),
    }.items():
        points[index] = point
    return points


def open_landmarks() -> list[FramePoint]:
    points = grab_landmarks()
    points[4] = FramePoint(0.20, 0.40)
    points[8] = FramePoint(0.25, 0.10)
    points[12] = FramePoint(0.45, 0.08)
    points[16] = FramePoint(0.63, 0.12)
    points[20] = FramePoint(0.78, 0.20)
    return points


def test_open_hand_does_not_activate_grab_scroll() -> None:
    detector = make_detector()

    result = detector.update(open_landmarks(), now_ms=0)

    assert result.state == GrabScrollState.RELEASED
    assert result.active is False
    assert result.scroll_delta == 0


def test_grab_pose_must_be_held_before_activation() -> None:
    detector = make_detector()

    first = detector.update(grab_landmarks(), now_ms=0)
    second = detector.update(grab_landmarks(), now_ms=50)
    third = detector.update(grab_landmarks(), now_ms=120)

    assert first.state == GrabScrollState.CANDIDATE
    assert first.active is False
    assert second.state == GrabScrollState.CANDIDATE
    assert second.active is False
    assert third.state == GrabScrollState.GRABBING
    assert third.active is True


def test_grab_drag_outputs_scroll_delta() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=120)
    result = detector.update(grab_landmarks(y_offset=-0.08), now_ms=160)

    assert result.state == GrabScrollState.DRAGGING
    assert result.scroll_delta == 12


def test_small_grab_motion_is_dead_zoned() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=120)
    result = detector.update(grab_landmarks(y_offset=0.005), now_ms=160)

    assert result.state == GrabScrollState.GRABBING
    assert result.scroll_delta == 0


def test_releasing_grab_resets_state() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=120)
    result = detector.update(open_landmarks(), now_ms=260)

    assert result.state == GrabScrollState.RELEASED
    assert result.active is False
    assert detector.update(grab_landmarks(y_offset=0.2), now_ms=280).state == GrabScrollState.CANDIDATE


def test_no_hand_resets_state() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=120)
    assert detector.update(None, now_ms=160).state == GrabScrollState.NO_HAND
    assert detector.update(grab_landmarks(y_offset=0.2), now_ms=180).state == GrabScrollState.CANDIDATE
