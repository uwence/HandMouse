from handmouse.hand_tracker import HandTrackingResult, MultiHandTrackingResult


def _make_result(label: str) -> HandTrackingResult:
    from handmouse.types import FramePoint
    lm = [FramePoint(0.5, 0.5)] * 21
    return HandTrackingResult(
        landmarks=lm,
        thumb_tip=lm[4],
        index_tip=lm[8],
        raw_landmarks=None,
        world_landmarks=None,
        handedness_label=label,
        handedness_confidence=0.9,
    )


def test_multi_first_returns_none_when_empty():
    m = MultiHandTrackingResult(hands=[])
    assert m.first is None


def test_multi_first_returns_first_hand():
    h = _make_result("Right")
    m = MultiHandTrackingResult(hands=[h])
    assert m.first is h


def test_multi_by_label_finds_correct_hand():
    left = _make_result("Left")
    right = _make_result("Right")
    m = MultiHandTrackingResult(hands=[left, right])
    assert m.by_label("Left") is left
    assert m.by_label("Right") is right
    assert m.by_label("Unknown") is None
