from handmouse.gesture_detector import GestureDetector, GestureConfig, GestureState
from handmouse.grab_scroll_detector import GrabScrollDetector, GrabScrollConfig, GrabScrollState
from handmouse.interlock import InteractionInterlock, InterlockType
from handmouse.types import FramePoint

def _create_mock_grab_landmarks() -> list[FramePoint]:
    landmarks = [FramePoint(0.5, 0.5)] * 21
    # wrist
    landmarks[0] = FramePoint(0.5, 0.9)
    # index mcp
    landmarks[5] = FramePoint(0.4, 0.5)
    # index tip
    landmarks[8] = FramePoint(0.4, 0.55)
    # middle mcp
    landmarks[9] = FramePoint(0.5, 0.5)
    # middle tip
    landmarks[12] = FramePoint(0.5, 0.55)
    # ring mcp
    landmarks[13] = FramePoint(0.6, 0.5)
    # ring tip
    landmarks[16] = FramePoint(0.6, 0.55)
    # pinky mcp
    landmarks[17] = FramePoint(0.7, 0.5)
    # pinky tip
    landmarks[20] = FramePoint(0.7, 0.55)
    # thumb tip
    landmarks[4] = FramePoint(0.45, 0.5)
    return landmarks

def test_click_suppresses_grab():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)
    
    # 1. Trigger pinch (click)
    thumb = FramePoint(0.5, 0.5)
    index = FramePoint(0.5, 0.5)  # distance 0 -> wants_active
    gesture.update(thumb, index, 100)
    gesture.update(thumb, index, 200) # second frame to enter PINCH_PRESSED
    
    assert interlock._state == InterlockType.CLICK
    assert gesture._state == GestureState.PINCH_PRESSED

    # 2. Try to trigger grab
    landmarks = _create_mock_grab_landmarks()
    res = grab.update(landmarks, 200)
    
    # Grab should be suppressed (NO_HAND state)
    assert res.state == GrabScrollState.NO_HAND
    assert interlock._state == InterlockType.CLICK

def test_grab_suppresses_click():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)
    
    # 1. Trigger grab
    landmarks = _create_mock_grab_landmarks()
    res = grab.update(landmarks, 100)
    
    assert interlock._state == InterlockType.GRAB
    assert res.state != GrabScrollState.NO_HAND

    # 2. Try to trigger click
    thumb = FramePoint(0.5, 0.5)
    index = FramePoint(0.5, 0.5)  # distance 0 -> wants_active
    gres = gesture.update(thumb, index, 200)
    
    # Click should be suppressed (PINCH_OPEN state)
    assert gres.state == GestureState.PINCH_OPEN
    assert interlock._state == InterlockType.GRAB

def test_releasing_one_allows_other():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)

    # 1. Trigger grab
    landmarks = _create_mock_grab_landmarks()
    grab.update(landmarks, 100)
    assert interlock._state == InterlockType.GRAB

    # 2. Release grab
    non_grab_landmarks = [FramePoint(0.5, 0.5)] * 21 # all points same spot -> not grab pose
    # First frame without grab (last_seen=100) -> state is RELEASED but not begun
    grab.update(non_grab_landmarks, 200)
    
    # Second frame: 300 - 100 = 200 > 120 (release_grace) -> _begin_release(300)
    grab.update(non_grab_landmarks, 300)
    
    # Third frame: 500 - 300 = 200 > 120 (post_release) -> _expire_release(500) -> NO_HAND
    grab.update(non_grab_landmarks, 500)

    # 3. Trigger click
    thumb = FramePoint(0.5, 0.5)
    index = FramePoint(0.5, 0.5)
    # Needs 2 frames for confirm_frames=2
    gesture.update(thumb, index, 600)
    gesture.update(thumb, index, 700)

    assert interlock._state == InterlockType.CLICK
