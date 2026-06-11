from handmouse.config import ShortcutConfig
from handmouse.shortcut_detector import ShortcutAction, ShortcutDetector
from handmouse.types import FramePoint
from handmouse.tracking.observation import HandObservation


CONFIG = ShortcutConfig(
    min_distance=0.2,
    max_duration_ms=500,
    axis_ratio=1.5,
    cooldown_ms=100,
)


def make_detector() -> ShortcutDetector:
    return ShortcutDetector(CONFIG)

def make_obs() -> HandObservation:
    return HandObservation(
        frame_id=1,
        ts_ms=0,
        image_landmarks=[],
        world_landmarks=[],
        handedness_label="Left",
        handedness_score=0.9,
        raw_result=None,
        stale_ms=0,
        camera_space="mirrored"
    )

def test_initial_no_hand() -> None:
    detector = make_detector()

    result = detector.update(None, now_ms=0, point=None)

    assert len(result) == 0


def test_first_frame_tracks_anchor() -> None:
    detector = make_detector()

    result = detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))

    assert len(result) == 0
    assert detector._anchor == FramePoint(0.5, 0.5)


def test_slow_movement_resets_anchor() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=600, point=FramePoint(0.6, 0.5))

    assert len(result) == 0
    assert detector._anchor == FramePoint(0.6, 0.5)
    assert detector._anchor_ms == 600


def test_swipe_left_emits_candidate() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.2, 0.5))

    assert len(result) == 1
    assert result[0].gesture == "swipe_left"
    assert result[0].measurements["dx"] == -0.3


import pytest

def test_swipe_right_emits_candidate() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.8, 0.5))

    assert len(result) == 1
    assert result[0].gesture == "swipe_right"
    assert result[0].measurements["dx"] == pytest.approx(0.3)


def test_swipe_up_emits_candidate() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.5, 0.2))

    assert len(result) == 1
    assert result[0].gesture == "swipe_up"
    assert result[0].measurements["dy"] == pytest.approx(-0.3)


def test_swipe_down_emits_candidate() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.5, 0.8))

    assert len(result) == 1
    assert result[0].gesture == "swipe_down"
    assert result[0].measurements["dy"] == pytest.approx(0.3)


def test_diagonal_swipe_ignored_when_ratio_not_met() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.8, 0.8))

    assert len(result) == 0


def test_cooldown_prevents_immediate_subsequent_swipes() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5))
    detector.update(make_obs(), now_ms=100, point=FramePoint(0.2, 0.5))
    
    first = detector.update(make_obs(), now_ms=150, point=FramePoint(0.2, 0.5))
    assert len(first) == 0

    detector.update(make_obs(), now_ms=250, point=FramePoint(0.5, 0.5))
    second = detector.update(make_obs(), now_ms=300, point=FramePoint(0.2, 0.5))
    assert len(second) == 1


def test_palm_open_modifiers_applied() -> None:
    detector = make_detector()

    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5), palm_open=True)
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.1, 0.5))

    assert len(result) == 1
    assert result[0].gesture == "swipe_left_palm"
