from __future__ import annotations

from handmouse.alt_tab_detector import AltTabDetector, AltTabState
from handmouse.types import FramePoint


def make_landmarks(index_ext: bool, middle_ext: bool, ring_ext: bool, pinky_ext: bool) -> list[FramePoint]:
    landmarks = [FramePoint(0.5, 0.5)] * 21
    # palm center elements
    landmarks[0] = FramePoint(0.5, 0.7)
    landmarks[5] = FramePoint(0.45, 0.6)
    landmarks[9] = FramePoint(0.50, 0.6)
    landmarks[13] = FramePoint(0.55, 0.6)
    landmarks[17] = FramePoint(0.60, 0.6)

    # index
    landmarks[8] = FramePoint(0.45, 0.2) if index_ext else FramePoint(0.45, 0.55)
    # middle
    landmarks[12] = FramePoint(0.50, 0.2) if middle_ext else FramePoint(0.50, 0.55)
    # ring
    landmarks[16] = FramePoint(0.55, 0.2) if ring_ext else FramePoint(0.55, 0.55)
    # pinky
    landmarks[20] = FramePoint(0.60, 0.2) if pinky_ext else FramePoint(0.60, 0.55)

    return landmarks


def test_alt_tab_pose_detection() -> None:
    detector = AltTabDetector(arming_time_ms=350)

    # 1. Start with non-alt-tab pose
    bad_landmarks = make_landmarks(index_ext=True, middle_ext=False, ring_ext=False, pinky_ext=False)
    state, is_alt_held = detector.update(bad_landmarks, now_ms=0)
    assert state == AltTabState.INACTIVE
    assert not is_alt_held

    # 2. Transition to arming with valid pose
    good_landmarks = make_landmarks(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=False)
    state, is_alt_held = detector.update(good_landmarks, now_ms=10)
    assert state == AltTabState.ARMING
    assert not is_alt_held

    # 3. Not enough time has passed
    state, is_alt_held = detector.update(good_landmarks, now_ms=100)
    assert state == AltTabState.ARMING
    assert not is_alt_held

    # 4. Triggers Alt+Tab after 350ms
    state, is_alt_held = detector.update(good_landmarks, now_ms=370)
    assert state == AltTabState.ACTIVE
    assert is_alt_held

    # 5. Navigates forward on right displacement
    # good_landmarks center is at 0.5. Shift center to 0.6 (rightwards)
    nav_right_landmarks = [FramePoint(pt.x + 0.1, pt.y) for pt in good_landmarks]
    state, is_alt_held = detector.update(nav_right_landmarks, now_ms=780)
    assert state == AltTabState.ACTIVE
    assert is_alt_held
    # Anchor should update, checking small diff now shouldn't navigate immediately again
    state, is_alt_held = detector.update(nav_right_landmarks, now_ms=790)
    assert state == AltTabState.ACTIVE

    # 6. Releases alt when pose is broken
    state, is_alt_held = detector.update(bad_landmarks, now_ms=800)
    assert state == AltTabState.INACTIVE
    assert not is_alt_held
