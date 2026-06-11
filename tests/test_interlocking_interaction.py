from handmouse.gesture_detector import GestureDetector, GestureConfig
from handmouse.grab_scroll_detector import GrabScrollDetector, GrabScrollConfig, GrabScrollState
from handmouse.interlock import InteractionInterlock, InterlockType
from handmouse.types import FramePoint
from handmouse.tracking.observation import HandObservation, Point3


def _create_mock_grab_landmarks(y_offset: float = 0.0) -> list[Point3]:
    points = [Point3(0.0, 0.0, 0.0) for _ in range(21)]
    for index, point in {
        0: Point3(0.50, 0.80 + y_offset, 0.0),
        4: Point3(0.36, 0.55 + y_offset, 0.0),
        5: Point3(0.40, 0.56 + y_offset, 0.0),
        8: Point3(0.45, 0.50 + y_offset, 0.0),
        9: Point3(0.50, 0.52 + y_offset, 0.0),
        12: Point3(0.52, 0.49 + y_offset, 0.0),
        13: Point3(0.60, 0.56 + y_offset, 0.0),
        16: Point3(0.57, 0.52 + y_offset, 0.0),
        17: Point3(0.68, 0.62 + y_offset, 0.0),
        20: Point3(0.62, 0.58 + y_offset, 0.0),
    }.items():
        points[index] = point
    return points

def make_obs(landmarks) -> HandObservation:
    return HandObservation(
        frame_id=1,
        ts_ms=0,
        image_landmarks=landmarks,
        world_landmarks=landmarks,
        handedness_label="Left",
        handedness_score=0.9,
        raw_result=None,
        stale_ms=0,
        camera_space="mirrored"
    )

def test_grab_overrides_click():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)

    # 1. Trigger pinch (click)
    landmarks = [Point3(0.5, 0.5, 0.0)] * 21
    landmarks[5] = Point3(0.5, 0.5, 0.0)
    landmarks[17] = Point3(0.5, 0.6, 0.0) # palm span
    landmarks[4] = Point3(0.5, 0.5, 0.0) # thumb
    landmarks[8] = Point3(0.5, 0.5, 0.0) # index
    
    gesture.update(make_obs(landmarks), 100)

    assert interlock.is_active is True
    assert interlock.current_owner == InterlockType.CLICK

    # 2. Try to grab while clicking - Grab should forcibly take over
    grab_landmarks = _create_mock_grab_landmarks()
    res = grab.update(make_obs(grab_landmarks), 100)

    assert len(res) == 0
    assert grab._state == GrabScrollState.CANDIDATE
    assert interlock.current_owner == InterlockType.GRAB


def test_grab_suppresses_click():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)

    # 1. Trigger grab
    landmarks = _create_mock_grab_landmarks()
    res = grab.update(make_obs(landmarks), 100)

    assert interlock.is_active is True

    # 2. Try to click while grabbing
    click_landmarks = [Point3(0.5, 0.5, 0.0)] * 21
    click_landmarks[5] = Point3(0.5, 0.5, 0.0)
    click_landmarks[17] = Point3(0.5, 0.6, 0.0)
    click_landmarks[4] = Point3(0.5, 0.5, 0.0)
    click_landmarks[8] = Point3(0.5, 0.5, 0.0)
    gesture_res = gesture.update(make_obs(click_landmarks), 100)

    assert len(gesture_res) == 0


def test_releasing_one_allows_other():
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)

    # 1. Trigger grab
    landmarks = _create_mock_grab_landmarks()
    grab.update(make_obs(landmarks), 100)
    assert interlock.is_active is True

    # 2. Release grab
    open_landmarks = [Point3(0.5, 0.5, 0.0)] * 21
    grab.update(make_obs(open_landmarks), 300)
    # wait out post release grace ms 120
    grab.update(None, 450)
    assert interlock.is_active is False

    # 3. Now click should work
    click_landmarks = [Point3(0.5, 0.5, 0.0)] * 21
    click_landmarks[5] = Point3(0.5, 0.5, 0.0)
    click_landmarks[17] = Point3(0.5, 0.6, 0.0)
    click_landmarks[4] = Point3(0.5, 0.5, 0.0)
    click_landmarks[8] = Point3(0.5, 0.5, 0.0)
    
    res = gesture.update(make_obs(click_landmarks), 500)
    assert interlock.is_active is True
