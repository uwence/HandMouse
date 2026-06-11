from handmouse.config import DEFAULT_CONFIG, ShortcutConfig
from handmouse.types import FramePoint
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


def test_detects_palm_swipes() -> None:
    """Horizontal swipes with palm_open=True emit SWIPE_*_PALM; the h_threshold
    is 1.5x base_threshold, so a 0.35-distance move crosses the palm threshold
    (0.3) and is detected as SWIPE_RIGHT_PALM."""
    # Baseline: 0.25 swipe without palm_open registers as SWIPE_RIGHT (threshold=0.2)
    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0, palm_open=False).action is None
    assert (
        detector.update(FramePoint(0.75, 0.5), now_ms=120, palm_open=False).action
        == ShortcutAction.SWIPE_RIGHT
    )

    # 0.25 swipe with palm_open=True is below palm threshold (0.3) and rejected
    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0, palm_open=True).action is None
    assert (
        detector.update(FramePoint(0.75, 0.5), now_ms=120, palm_open=True).action
        is None
    )

    # 0.35 swipe with palm_open=True crosses palm threshold (0.3) and triggers SWIPE_RIGHT_PALM
    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0, palm_open=True).action is None
    assert (
        detector.update(FramePoint(0.85, 0.5), now_ms=120, palm_open=True).action
        == ShortcutAction.SWIPE_RIGHT_PALM
    )

    # Symmetric: SWIPE_LEFT_PALM
    detector = make_detector()
    assert detector.update(FramePoint(0.5, 0.5), now_ms=0, palm_open=True).action is None
    assert (
        detector.update(FramePoint(0.15, 0.5), now_ms=120, palm_open=True).action
        == ShortcutAction.SWIPE_LEFT_PALM
    )

