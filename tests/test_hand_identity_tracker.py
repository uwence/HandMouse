from handmouse.hand_tracker import HandTrackingResult, MultiHandTrackingResult
from handmouse.tracking.identity import HandIdentityTracker, IdentifiedHands
from handmouse.types import FramePoint


def _make_hand(label: str) -> HandTrackingResult:
    from handmouse.tracking.observation import Point3
    lm_frame = [FramePoint(0.5, 0.5)] * 21
    lm_world = [Point3(0.0, 0.0, 0.0)] * 21
    return HandTrackingResult(
        landmarks=lm_frame,
        thumb_tip=lm_frame[4],
        index_tip=lm_frame[8],
        raw_landmarks=None,
        world_landmarks=lm_world,
        handedness_label=label,
        handedness_confidence=0.95,
    )


def _multi(*labels: str) -> MultiHandTrackingResult:
    return MultiHandTrackingResult(hands=[_make_hand(lb) for lb in labels])


def test_both_hands_identified():
    tracker = HandIdentityTracker(grace_ms=200)
    result = tracker.update(_multi("Left", "Right"), now_ms=0, frame_age_ms=5)
    assert result.left_obs is not None
    assert result.right_obs is not None


def test_only_right_identified():
    tracker = HandIdentityTracker(grace_ms=200)
    result = tracker.update(_multi("Right"), now_ms=0, frame_age_ms=5)
    assert result.left_obs is None
    assert result.right_obs is not None


def test_hand_persists_within_grace_period():
    tracker = HandIdentityTracker(grace_ms=200)
    tracker.update(_multi("Left", "Right"), now_ms=0, frame_age_ms=5)
    # Left disappears at t=100, still within 200ms grace
    result = tracker.update(_multi("Right"), now_ms=100, frame_age_ms=5)
    assert result.left_obs is not None, "left should persist within grace"
    assert result.right_obs is not None


def test_hand_evicted_after_grace_period():
    tracker = HandIdentityTracker(grace_ms=200)
    tracker.update(_multi("Left", "Right"), now_ms=0, frame_age_ms=5)
    # Left disappears; jump past grace period
    result = tracker.update(_multi("Right"), now_ms=300, frame_age_ms=5)
    assert result.left_obs is None, "left should be evicted after grace"


def test_result_has_raw_results_for_pointer_engine():
    tracker = HandIdentityTracker(grace_ms=200)
    result = tracker.update(_multi("Left", "Right"), now_ms=0, frame_age_ms=5)
    assert result.left_result is not None
    assert result.right_result is not None
    assert result.left_result.handedness_label == "Left"
