from __future__ import annotations

from handmouse.alt_tab_detector import AltTabDetector, AltTabState
from handmouse.types import FramePoint
from handmouse.policy.gesture_policy import RiskClass


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
    candidates = detector.update(bad_landmarks, now_ms=0)
    assert detector.state == AltTabState.INACTIVE
    assert len(candidates) == 0

    # 2. Transition to arming with valid pose
    good_landmarks = make_landmarks(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=False)
    candidates = detector.update(good_landmarks, now_ms=10)
    assert detector.state == AltTabState.ARMING
    assert len(candidates) == 1
    assert candidates[0].phase == "candidate"

    # 3. Not enough time has passed
    candidates = detector.update(good_landmarks, now_ms=100)
    assert detector.state == AltTabState.ARMING
    assert len(candidates) == 1
    assert candidates[0].phase == "armed"

    # 4. Triggers Alt+Tab after 350ms
    candidates = detector.update(good_landmarks, now_ms=370)
    assert detector.state == AltTabState.ACTIVE
    assert len(candidates) == 1
    assert candidates[0].phase == "fire"
    assert candidates[0].gesture == "task_view"

    # 5. Navigates forward on right displacement
    # good_landmarks center is at 0.5. Shift center to 0.6 (rightwards)
    nav_right_landmarks = [FramePoint(pt.x + 0.1, pt.y) for pt in good_landmarks]
    candidates = detector.update(nav_right_landmarks, now_ms=780)
    assert detector.state == AltTabState.ACTIVE
    assert any(c.phase == "fire" and c.gesture == "nav_right" for c in candidates)
    
    # Anchor should update, checking small diff now shouldn't navigate immediately again
    candidates = detector.update(nav_right_landmarks, now_ms=790)
    assert detector.state == AltTabState.ACTIVE
    assert not any(c.phase == "fire" and c.gesture.startswith("nav") for c in candidates)

    # 6. Pose loss cancels task view instead of committing
    candidates = detector.update(bad_landmarks, now_ms=800)
    assert detector.state == AltTabState.INACTIVE
    assert len(candidates) == 1
    assert candidates[0].phase == "cancel"
    assert candidates[0].gesture == "task_view_cancel"


def test_alt_tab_commit_requires_explicit_confirm_pinch() -> None:
    detector = AltTabDetector(arming_time_ms=100)
    good_landmarks = make_landmarks(index_ext=True, middle_ext=True, ring_ext=True, pinky_ext=False)

    detector.update(good_landmarks, now_ms=0)
    detector.update(good_landmarks, now_ms=50)
    detector.update(good_landmarks, now_ms=120)

    commit_landmarks = list(good_landmarks)
    commit_landmarks[4] = FramePoint(commit_landmarks[8].x + 0.01, commit_landmarks[8].y)

    candidates = detector.update(commit_landmarks, now_ms=250)

    assert detector.state == AltTabState.INACTIVE
    assert any(c.phase == "fire" and c.gesture == "task_view_commit" for c in candidates)
