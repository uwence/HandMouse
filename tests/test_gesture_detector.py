from handmouse.config import GestureConfig
from handmouse.gesture_detector import GestureDetector, GestureState
from handmouse.pointer_mapper import FramePoint


CONFIG = GestureConfig(
    pinch_threshold=0.05,
    hold_ms=120,
    cooldown_ms=350,
    release_threshold=0.08,
)

THUMB = FramePoint(0.5, 0.5)
PINCHED_INDEX = FramePoint(0.53, 0.5)
RELEASED_INDEX = FramePoint(0.7, 0.5)


def make_detector() -> GestureDetector:
    return GestureDetector(CONFIG)


def test_no_hand_returns_no_hand_and_no_click() -> None:
    detector = make_detector()

    result = detector.update(None, None, now_ms=0)

    assert result.state == GestureState.NO_HAND
    assert result.should_click is False
    assert result.pinch_distance is None


def test_short_pinch_does_not_click() -> None:
    detector = make_detector()

    first = detector.update(THUMB, PINCHED_INDEX, now_ms=0)
    short = detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms - 1)

    assert first.state == GestureState.PINCH_CANDIDATE
    assert first.should_click is False
    assert short.state == GestureState.PINCH_CANDIDATE
    assert short.should_click is False


def test_held_pinch_emits_exactly_one_click() -> None:
    detector = make_detector()

    results = [
        detector.update(THUMB, PINCHED_INDEX, now_ms=0),
        detector.update(THUMB, PINCHED_INDEX, now_ms=60),
        detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms),
        detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms + 1),
    ]

    assert [result.should_click for result in results].count(True) == 1
    assert results[2].state == GestureState.CLICK
    assert results[2].should_click is True


def test_continuing_to_hold_during_cooldown_does_not_repeat() -> None:
    detector = make_detector()

    click = detector.update(THUMB, PINCHED_INDEX, now_ms=0)
    click = detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms)
    during_cooldown = detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms + 100)
    after_cooldown_still_pinched = detector.update(
        THUMB,
        PINCHED_INDEX,
        now_ms=CONFIG.hold_ms + CONFIG.cooldown_ms + 1,
    )

    assert click.should_click is True
    assert during_cooldown.state == GestureState.COOLDOWN
    assert during_cooldown.should_click is False
    assert after_cooldown_still_pinched.state == GestureState.COOLDOWN
    assert after_cooldown_still_pinched.should_click is False


def test_releasing_after_cooldown_allows_a_new_click() -> None:
    detector = make_detector()

    first_click = detector.update(THUMB, PINCHED_INDEX, now_ms=0)
    first_click = detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms)
    release = detector.update(
        THUMB,
        RELEASED_INDEX,
        now_ms=CONFIG.hold_ms + CONFIG.cooldown_ms,
    )
    new_candidate = detector.update(
        THUMB,
        PINCHED_INDEX,
        now_ms=CONFIG.hold_ms + CONFIG.cooldown_ms + 10,
    )
    second_click = detector.update(
        THUMB,
        PINCHED_INDEX,
        now_ms=CONFIG.hold_ms + CONFIG.cooldown_ms + 10 + CONFIG.hold_ms,
    )

    assert first_click.should_click is True
    assert release.state == GestureState.MOVING
    assert release.should_click is False
    assert new_candidate.state == GestureState.PINCH_CANDIDATE
    assert new_candidate.should_click is False
    assert second_click.state == GestureState.CLICK
    assert second_click.should_click is True


def test_missing_landmark_resets_pending_pinch() -> None:
    detector = make_detector()

    detector.update(THUMB, PINCHED_INDEX, now_ms=0)
    no_hand = detector.update(THUMB, None, now_ms=60)
    restarted = detector.update(THUMB, PINCHED_INDEX, now_ms=CONFIG.hold_ms)

    assert no_hand.state == GestureState.NO_HAND
    assert no_hand.should_click is False
    assert restarted.state == GestureState.PINCH_CANDIDATE
    assert restarted.should_click is False
