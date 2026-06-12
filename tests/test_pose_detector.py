from handmouse.tracking.observation import HandObservation, Point3
from handmouse.pose_detector import PoseDetector


def _obs(landmarks: list[Point3]) -> HandObservation:
    return HandObservation(
        frame_id=1,
        ts_ms=0,
        image_landmarks=landmarks,
        world_landmarks=None,
        handedness_label="Right",
        handedness_score=0.9,
        raw_result=None,
        stale_ms=0,
        camera_space="mirrored",
    )


def _flat_landmarks(n: int = 21) -> list[Point3]:
    return [Point3(0.5, 0.5, 0.0)] * n


def _palm_open_landmarks() -> list[Point3]:
    """All 4 fingertips far from palm center (extended upward)."""
    lm = list(_flat_landmarks())
    # Wrist at y=0.8, MCPs at y=0.6
    lm[0] = Point3(0.5, 0.8, 0.0)   # wrist
    for i in (5, 9, 13, 17):
        lm[i] = Point3(0.5, 0.6, 0.0)  # MCPs
    # Fingertips far from palm center (y=0.1 = extended)
    for tip_i in (8, 12, 16, 20):
        lm[tip_i] = Point3(0.5, 0.1, 0.0)
    return lm


def _fist_landmarks() -> list[Point3]:
    """All fingertips close to wrist (curled)."""
    lm = list(_flat_landmarks())
    lm[0] = Point3(0.5, 0.8, 0.0)   # wrist
    for i in (5, 9, 13, 17):
        lm[i] = Point3(0.5, 0.6, 0.0)  # MCPs
    # Fingertips curled close to palm center (y=0.64)
    for tip_i in (8, 12, 16, 20):
        lm[tip_i] = Point3(0.5, 0.65, 0.0)
    return lm


def _palm_open_only_2_extended_landmarks() -> list[Point3]:
    """Only 2 fingertips extended, 2 curled (below MIN_FINGERS=3 threshold)."""
    lm = list(_flat_landmarks())
    lm[0] = Point3(0.5, 0.8, 0.0)   # wrist
    for i in (5, 9, 13, 17):
        lm[i] = Point3(0.5, 0.6, 0.0)  # MCPs
    # Only 2 fingertips extended (indices 8 and 12)
    lm[8] = Point3(0.5, 0.1, 0.0)
    lm[12] = Point3(0.5, 0.1, 0.0)
    # Other 2 fingertips curled (indices 16 and 20)
    lm[16] = Point3(0.5, 0.65, 0.0)
    lm[20] = Point3(0.5, 0.65, 0.0)
    return lm


def _fist_only_2_curled_landmarks() -> list[Point3]:
    """Only 2 fingertips curled, 2 extended (below MIN_FINGERS=3 threshold)."""
    lm = list(_flat_landmarks())
    lm[0] = Point3(0.5, 0.8, 0.0)   # wrist
    for i in (5, 9, 13, 17):
        lm[i] = Point3(0.5, 0.6, 0.0)  # MCPs
    # Only 2 fingertips curled (indices 8 and 12)
    lm[8] = Point3(0.5, 0.65, 0.0)
    lm[12] = Point3(0.5, 0.65, 0.0)
    # Other 2 fingertips extended (indices 16 and 20)
    lm[16] = Point3(0.5, 0.1, 0.0)
    lm[20] = Point3(0.5, 0.1, 0.0)
    return lm


def test_palm_open_returns_true_for_extended_fingers():
    obs = _obs(_palm_open_landmarks())
    assert PoseDetector.is_palm_open(obs) is True


def test_palm_open_returns_false_for_fist():
    obs = _obs(_fist_landmarks())
    assert PoseDetector.is_palm_open(obs) is False


def test_fist_returns_true_for_curled_fingers():
    obs = _obs(_fist_landmarks())
    assert PoseDetector.is_fist(obs) is True


def test_fist_returns_false_for_open_palm():
    obs = _obs(_palm_open_landmarks())
    assert PoseDetector.is_fist(obs) is False


def test_returns_false_for_insufficient_landmarks():
    obs = _obs([Point3(0.5, 0.5, 0.0)] * 5)
    assert PoseDetector.is_palm_open(obs) is False
    assert PoseDetector.is_fist(obs) is False


def test_palm_open_false_with_only_2_extended():
    obs = _obs(_palm_open_only_2_extended_landmarks())
    assert PoseDetector.is_palm_open(obs) is False


def test_fist_false_with_only_2_curled():
    obs = _obs(_fist_only_2_curled_landmarks())
    assert PoseDetector.is_fist(obs) is False


def test_empty_landmark_list():
    obs = _obs([])
    assert PoseDetector.is_palm_open(obs) is False
    assert PoseDetector.is_fist(obs) is False
