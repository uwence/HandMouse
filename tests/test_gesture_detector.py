from handmouse.gesture_detector import GestureConfig, GestureDetector, GestureState
from handmouse.types import FramePoint


CONFIG = GestureConfig(
    pinch_close=0.05,
    pinch_open=0.075,
    confirm_frames=2,
    release_confirm_frames=2,
    cooldown_ms=100,
)

THUMB = FramePoint(0.5, 0.5)
CLOSED_INDEX = FramePoint(0.53, 0.5)
JITTER_INDEX = FramePoint(0.56, 0.5)
OPEN_INDEX = FramePoint(0.70, 0.5)


def make_detector() -> GestureDetector:
    return GestureDetector(CONFIG)


def pinch(detector: GestureDetector, now_ms: int, index: FramePoint = CLOSED_INDEX):
    return detector.update(THUMB, index, now_ms=now_ms)


def test_initial_state_open() -> None:
    detector = make_detector()

    result = detector.update(None, None, now_ms=0)

    assert result.state == GestureState.PINCH_OPEN
    assert result.should_click is False
    assert result.pinch_distance is None


def test_open_to_pressed_after_close_confirm_frames() -> None:
    detector = make_detector()

    first = pinch(detector, now_ms=0)
    second = pinch(detector, now_ms=10)

    assert first.state == GestureState.PINCH_OPEN
    assert first.should_click is False
    assert second.state == GestureState.PINCH_PRESSED
    assert second.should_click is False


def test_short_pinch_does_not_press() -> None:
    detector = make_detector()

    first = pinch(detector, now_ms=0)
    released = detector.update(THUMB, OPEN_INDEX, now_ms=10)

    assert first.state == GestureState.PINCH_OPEN
    assert first.should_click is False
    assert released.state == GestureState.PINCH_OPEN
    assert released.should_click is False


def test_pressed_to_hold_when_distance_stays_small() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    pressed = pinch(detector, now_ms=10)
    held = pinch(detector, now_ms=20)

    assert pressed.state == GestureState.PINCH_PRESSED
    assert held.state == GestureState.PINCH_HOLD
    assert held.should_click is False


def test_hold_to_emit_click_on_release() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    pinch(detector, now_ms=10)
    pinch(detector, now_ms=20)
    release_1 = detector.update(THUMB, OPEN_INDEX, now_ms=30)
    release_2 = detector.update(THUMB, OPEN_INDEX, now_ms=40)

    assert release_1.state == GestureState.PINCH_HOLD
    assert release_1.should_click is False
    assert release_2.state == GestureState.COOLDOWN
    assert release_2.should_click is True


def test_double_click_requires_two_releases() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    pinch(detector, now_ms=10)
    pinch(detector, now_ms=20)
    first_release_1 = detector.update(THUMB, OPEN_INDEX, now_ms=30)
    first_release_2 = detector.update(THUMB, OPEN_INDEX, now_ms=40)
    suppressed_1 = detector.update(THUMB, OPEN_INDEX, now_ms=60)
    suppressed_2 = detector.update(THUMB, OPEN_INDEX, now_ms=80)
    second_press_1 = detector.update(THUMB, CLOSED_INDEX, now_ms=200)
    second_press_2 = detector.update(THUMB, CLOSED_INDEX, now_ms=210)
    second_hold = detector.update(THUMB, CLOSED_INDEX, now_ms=220)
    second_release_1 = detector.update(THUMB, OPEN_INDEX, now_ms=230)
    second_release_2 = detector.update(THUMB, OPEN_INDEX, now_ms=240)

    assert first_release_1.should_click is False
    assert first_release_1.state == GestureState.PINCH_HOLD
    assert first_release_2.state == GestureState.COOLDOWN
    assert first_release_2.should_click is True
    assert suppressed_1.state == GestureState.COOLDOWN
    assert suppressed_1.should_click is False
    assert suppressed_2.state == GestureState.COOLDOWN
    assert suppressed_2.should_click is False
    assert second_press_1.state == GestureState.PINCH_OPEN
    assert second_press_1.should_click is False
    assert second_press_2.state == GestureState.PINCH_PRESSED
    assert second_hold.state == GestureState.PINCH_HOLD
    assert second_release_1.state == GestureState.PINCH_HOLD
    assert second_release_2.state == GestureState.COOLDOWN
    assert second_release_2.should_double_click is True


def test_cooldown_suppresses_repeat_clicks() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    pinch(detector, now_ms=10)
    pinch(detector, now_ms=20)
    detector.update(THUMB, OPEN_INDEX, now_ms=30)
    click = detector.update(THUMB, OPEN_INDEX, now_ms=40)
    suppressed = detector.update(THUMB, OPEN_INDEX, now_ms=60)

    assert click.state == GestureState.COOLDOWN
    assert click.should_click is True
    assert suppressed.state == GestureState.COOLDOWN
    assert suppressed.should_click is False


def test_no_hand_resets_to_open() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    reset = detector.update(None, None, now_ms=10)
    restarted = pinch(detector, now_ms=20)

    assert reset.state == GestureState.PINCH_OPEN
    assert reset.should_click is False
    assert restarted.state == GestureState.PINCH_OPEN
    assert restarted.should_click is False


def test_hysteresis_short_distance_jitter_does_not_flip_state() -> None:
    detector = make_detector()

    pinch(detector, now_ms=0)
    pinch(detector, now_ms=10)
    jitter_1 = detector.update(THUMB, JITTER_INDEX, now_ms=20)
    jitter_2 = detector.update(THUMB, FramePoint(0.57, 0.5), now_ms=30)
    jitter_3 = detector.update(THUMB, FramePoint(0.58, 0.5), now_ms=40)

    assert jitter_1.state == GestureState.PINCH_HOLD
    assert jitter_2.state == GestureState.PINCH_HOLD
    assert jitter_3.state == GestureState.PINCH_HOLD
    assert jitter_1.should_click is False
    assert jitter_2.should_click is False
    assert jitter_3.should_click is False


def test_right_click_gesture() -> None:
    detector = make_detector()
    middle_closed = CLOSED_INDEX

    # Pinch middle finger (right click)
    first = detector.update(THUMB, OPEN_INDEX, now_ms=0, middle=middle_closed)
    second = detector.update(THUMB, OPEN_INDEX, now_ms=10, middle=middle_closed)
    assert first.right_state == GestureState.PINCH_OPEN
    assert second.right_state == GestureState.PINCH_PRESSED

    # Hold right pinch
    held = detector.update(THUMB, OPEN_INDEX, now_ms=20, middle=middle_closed)
    assert held.right_state == GestureState.PINCH_HOLD
    assert held.should_right_click is False

    # Release right pinch
    rel1 = detector.update(THUMB, OPEN_INDEX, now_ms=30, middle=OPEN_INDEX)
    rel2 = detector.update(THUMB, OPEN_INDEX, now_ms=40, middle=OPEN_INDEX)
    assert rel1.right_state == GestureState.PINCH_HOLD
    assert rel2.right_state == GestureState.COOLDOWN
    assert rel2.should_right_click is True


def test_left_and_right_click_mutual_exclusion() -> None:
    detector = make_detector()

    # Left pinch starts
    detector.update(THUMB, CLOSED_INDEX, now_ms=0)
    left_pressed = detector.update(THUMB, CLOSED_INDEX, now_ms=10)
    assert left_pressed.state == GestureState.PINCH_PRESSED

    # While left is active, try to pinch right
    result = detector.update(THUMB, CLOSED_INDEX, now_ms=20, middle=CLOSED_INDEX)
    assert result.state == GestureState.PINCH_HOLD  # Left stays active
    assert result.right_state == GestureState.PINCH_OPEN  # Right is blocked/reset
