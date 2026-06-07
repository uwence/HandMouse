from handmouse.config import DEFAULT_CONFIG, ShortcutConfig
from handmouse.pointer_mapper import FramePoint
from handmouse.shortcut_detector import (
    ShortcutAction,
    ShortcutDetector,
    ShortcutState,
)


def make_detector() -> ShortcutDetector:
    return ShortcutDetector(
        ShortcutConfig(
            min_distance=0.2,
            max_duration_ms=500,
            cooldown_ms=300,
            axis_ratio=1.4,
        )
    )


def test_first_point_starts_tracking_without_action() -> None:
    detector = make_detector()

    result = detector.update(FramePoint(0.5, 0.5), now_ms=0)

    assert result.state == ShortcutState.TRACKING
    assert result.action is None


def test_detects_horizontal_swipes() -> None:
    detector = make_detector()

    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    assert detector.update(FramePoint(0.75, 0.5), now_ms=120).action == ShortcutAction.SWIPE_RIGHT

    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    assert detector.update(FramePoint(0.25, 0.5), now_ms=120).action == ShortcutAction.SWIPE_LEFT


def test_detects_vertical_swipes() -> None:
    detector = make_detector()

    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    assert detector.update(FramePoint(0.5, 0.25), now_ms=120).action == ShortcutAction.SWIPE_UP

    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    assert detector.update(FramePoint(0.5, 0.75), now_ms=120).action == ShortcutAction.SWIPE_DOWN


def test_ignores_diagonal_motion() -> None:
    detector = make_detector()

    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    result = detector.update(FramePoint(0.75, 0.75), now_ms=120)

    assert result.state == ShortcutState.TRACKING
    assert result.action is None


def test_slow_motion_resets_anchor_without_action() -> None:
    detector = make_detector()

    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    result = detector.update(FramePoint(0.9, 0.5), now_ms=700)

    assert result.state == ShortcutState.TRACKING
    assert result.action is None


def test_cooldown_prevents_repeated_action() -> None:
    detector = make_detector()

    detector.update(FramePoint(0.5, 0.5), now_ms=0)
    assert detector.update(FramePoint(0.75, 0.5), now_ms=120).action == ShortcutAction.SWIPE_RIGHT

    result = detector.update(FramePoint(0.2, 0.5), now_ms=200)

    assert result.state == ShortcutState.COOLDOWN
    assert result.action is None


def test_no_hand_resets_anchor() -> None:
    detector = make_detector()

    detector.update(FramePoint(0.5, 0.5), now_ms=0)
    assert detector.update(None, now_ms=50).state == ShortcutState.NO_HAND
    assert detector.update(FramePoint(0.9, 0.5), now_ms=100).action is None


def test_default_config_detects_moderate_swipe_amplitude() -> None:
    detector = ShortcutDetector(DEFAULT_CONFIG.shortcut)

    assert detector.update(FramePoint(0.5, 0.5), now_ms=0).action is None
    assert detector.update(FramePoint(0.67, 0.5), now_ms=120).action is None
    assert detector.update(FramePoint(0.69, 0.5), now_ms=240).action == ShortcutAction.SWIPE_RIGHT
