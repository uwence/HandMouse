from handmouse.grab_scroll_detector import (
    GrabScrollConfig,
    GrabScrollDetector,
    GrabScrollState,
)
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
        post_release_grace_ms=120,
        only_active_when_draging=True,
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


def test_initial_no_hand() -> None:
    detector = make_detector()

    result = detector.update(None, now_ms=0)

    assert result.state == GrabScrollState.NO_HAND
    assert result.active is False
    assert result.scroll_delta == 0


def test_grab_pose_enters_candidate() -> None:
    detector = make_detector()

    result = detector.update(grab_landmarks(), now_ms=0)

    assert result.state == GrabScrollState.CANDIDATE
    assert result.active is False
    assert result.is_grab_pose is True


def test_hold_then_move_enters_dragging() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    result = detector.update(grab_landmarks(y_offset=-0.08), now_ms=140)

    assert result.state == GrabScrollState.DRAGGING
    assert result.scroll_delta == 12
    assert result.active is True


def test_release_exits_to_released() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    detector.update(grab_landmarks(y_offset=-0.08), now_ms=140)

    result = detector.update(open_landmarks(), now_ms=260)

    assert result.state == GrabScrollState.RELEASED
    assert result.active is False
    assert result.scroll_delta == 0


def test_static_grab_hold_does_not_emit_scroll() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    result = detector.update(grab_landmarks(), now_ms=160)

    assert result.state == GrabScrollState.GRABBING
    assert result.scroll_delta == 0
    assert result.active is False


def test_active_only_true_when_dragging() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    hold = detector.update(grab_landmarks(), now_ms=160)
    drag = detector.update(grab_landmarks(y_offset=-0.08), now_ms=200)

    assert hold.state == GrabScrollState.GRABBING
    assert hold.active is False
    assert drag.state == GrabScrollState.DRAGGING
    assert drag.active is True
    assert drag.scroll_delta != 0


def test_release_grace_preserves_anchor_during_brief_loss() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    first_drag = detector.update(grab_landmarks(y_offset=-0.08), now_ms=140)
    missing = detector.update(None, now_ms=180)
    resumed = detector.update(grab_landmarks(y_offset=-0.12), now_ms=210)

    assert first_drag.state == GrabScrollState.DRAGGING
    assert missing.state == GrabScrollState.RELEASED
    assert missing.active is False
    assert resumed.state == GrabScrollState.DRAGGING
    assert resumed.active is True
    assert resumed.scroll_delta != 0


def test_post_release_grace_smooths_re_grab() -> None:
    detector = make_detector()

    detector.update(grab_landmarks(), now_ms=0)
    detector.update(grab_landmarks(), now_ms=100)
    detector.update(grab_landmarks(y_offset=-0.08), now_ms=140)
    released = detector.update(open_landmarks(), now_ms=260)
    regrab = detector.update(grab_landmarks(y_offset=-0.12), now_ms=310)

    assert released.state == GrabScrollState.RELEASED
    assert regrab.state == GrabScrollState.DRAGGING
    assert regrab.active is True
    assert regrab.scroll_delta != 0
