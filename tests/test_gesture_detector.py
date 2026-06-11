from handmouse.gesture_detector import GestureConfig, GestureDetector, GestureState
from handmouse.types import FramePoint
from handmouse.tracking.observation import HandObservation


CONFIG = GestureConfig(
    pinch_close_ratio=0.5,
    pinch_open_ratio=0.7,
    confirm_frames=2,
    release_confirm_frames=2,
    cooldown_ms=100,
)

def make_detector() -> GestureDetector:
    return GestureDetector(CONFIG)

def make_obs(
    thumb_x=0.5,
    thumb_y=0.5,
    index_x=0.8,
    index_y=0.5,
    middle_x=0.8,
    middle_y=0.5,
) -> HandObservation:
    from handmouse.tracking.observation import Point3
    landmarks = [Point3(0.5, 0.5, 0.0)] * 21
    # palm span points
    landmarks[5] = Point3(0.5, 0.5, 0.0)
    landmarks[17] = Point3(0.5, 0.6, 0.0) # palm_span = 0.1

    # thumb, index, middle
    landmarks[4] = Point3(thumb_x, thumb_y, 0.0)
    landmarks[8] = Point3(index_x, index_y, 0.0)
    landmarks[12] = Point3(middle_x, middle_y, 0.0)

    return HandObservation(
        frame_id=1,
        ts_ms=0,
        image_landmarks=landmarks,
        world_landmarks=landmarks,
        handedness_label="Left",
        handedness_score=0.9,
        raw_result=None,
        stale_ms=0,
        camera_space="mirrored",
    )

def test_initial_state_open() -> None:
    detector = make_detector()
    candidates = detector.update(None, now_ms=0)
    assert len(candidates) == 0
    assert detector._left_state == GestureState.PINCH_OPEN

def test_open_to_pressed_after_close_confirm_frames() -> None:
    detector = make_detector()
    obs = make_obs(thumb_x=0.5, index_x=0.53) # dist=0.03, ratio=0.3 < 0.5
    
    first = detector.update(obs, now_ms=0)
    second = detector.update(obs, now_ms=10)

    assert detector._left_state == GestureState.PINCH_PRESSED
    assert first == []
    assert second == []

def test_short_pinch_does_not_press() -> None:
    detector = make_detector()
    
    closed = make_obs(thumb_x=0.5, index_x=0.53)
    open_obs = make_obs(thumb_x=0.5, index_x=0.6) # dist=0.1, ratio=1.0 > 0.7

    detector.update(closed, now_ms=0)
    released = detector.update(open_obs, now_ms=10)

    assert detector._left_state == GestureState.PINCH_OPEN
    assert len(released) == 0

def test_pressed_to_hold_when_distance_stays_small() -> None:
    detector = make_detector()
    obs = make_obs(thumb_x=0.5, index_x=0.53)

    detector.update(obs, now_ms=0)
    detector.update(obs, now_ms=10)
    detector.update(obs, now_ms=20)

    assert detector._left_state == GestureState.PINCH_HOLD

def test_hold_to_emit_click_on_release() -> None:
    detector = make_detector()
    closed = make_obs(thumb_x=0.5, index_x=0.53)
    open_obs = make_obs(thumb_x=0.5, index_x=0.6)

    detector.update(closed, now_ms=0)
    detector.update(closed, now_ms=10)
    detector.update(closed, now_ms=20)
    
    c1 = detector.update(open_obs, now_ms=30)
    c2 = detector.update(open_obs, now_ms=40)

    assert detector._left_state == GestureState.COOLDOWN
    assert any(c.gesture == "click_left" for c in c2)
    assert not any(c.gesture == "drag_hold" for c in c2)
    assert not any(c.gesture == "drag_release" for c in c2)

def test_drag_starts_only_after_hold_and_movement_threshold() -> None:
    detector = make_detector()
    closed = make_obs(thumb_x=0.5, index_x=0.53)
    moved_while_pinched = make_obs(thumb_x=0.68, index_x=0.71)
    open_obs = make_obs(thumb_x=0.5, index_x=0.6)

    detector.update(closed, now_ms=0)
    detector.update(closed, now_ms=10)
    detector.update(closed, now_ms=20)

    drag_start = detector.update(moved_while_pinched, now_ms=30)
    detector.update(open_obs, now_ms=40)
    release = detector.update(open_obs, now_ms=50)

    assert detector._left_state == GestureState.COOLDOWN
    assert any(c.gesture == "drag_hold" for c in drag_start)
    assert any(c.gesture == "drag_release" for c in release)
    assert not any(c.gesture == "click_left" for c in release)

def test_double_click_requires_two_releases() -> None:
    detector = make_detector()
    closed = make_obs(thumb_x=0.5, index_x=0.53)
    open_obs = make_obs(thumb_x=0.5, index_x=0.6)

    # First click
    detector.update(closed, now_ms=0)
    detector.update(closed, now_ms=10)
    detector.update(closed, now_ms=20)
    detector.update(open_obs, now_ms=30)
    c_release_1 = detector.update(open_obs, now_ms=40)
    assert any(c.gesture == "click_left" for c in c_release_1)

    detector.update(open_obs, now_ms=60)
    detector.update(open_obs, now_ms=80)
    
    # Second click within 300ms (at 240ms)
    detector.update(closed, now_ms=200)
    detector.update(closed, now_ms=210)
    detector.update(closed, now_ms=220)
    detector.update(open_obs, now_ms=230)
    c_release_2 = detector.update(open_obs, now_ms=240)
    
    assert any(c.gesture == "double_click" for c in c_release_2)

def test_right_click_gesture() -> None:
    detector = make_detector()
    # middle closed: dist=0.03, index open: dist=0.1
    obs_closed = make_obs(thumb_x=0.5, index_x=0.6, middle_x=0.53)
    obs_open = make_obs(thumb_x=0.5, index_x=0.6, middle_x=0.6)

    detector.update(obs_closed, now_ms=0)
    detector.update(obs_closed, now_ms=10)
    detector.update(obs_closed, now_ms=20)
    
    detector.update(obs_open, now_ms=30)
    rel2 = detector.update(obs_open, now_ms=40)

    assert any(c.gesture == "click_right" for c in rel2)
