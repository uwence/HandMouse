from __future__ import annotations

from types import ModuleType, SimpleNamespace
import sys

import pytest

from handmouse.hand_tracker import HandTracker


class FakeLandmark:
    def __init__(self, x: float, y: float) -> None:
        self.x = x
        self.y = y


class FakeClassification:
    def __init__(self, category_name: str, score: float) -> None:
        self.category_name = category_name
        self.score = score


class FakeResult:
    def __init__(self, hand_landmarks: list[list[FakeLandmark]], handedness: list[list[FakeClassification]]) -> None:
        self.hand_landmarks = hand_landmarks
        self.handedness = handedness


class FakeLandmarker:
    def __init__(self, result: FakeResult) -> None:
        self.result = result
        self.calls: list[tuple[object, int]] = []
        self.closed = False

    def detect_for_video(self, mp_image: object, frame_timestamp_ms: int) -> FakeResult:
        self.calls.append((mp_image, frame_timestamp_ms))
        return self.result

    def close(self) -> None:
        self.closed = True


class FakeHandLandmarkerOptions:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs


class FakeBaseOptions:
    def __init__(self, model_asset_path: str) -> None:
        self.model_asset_path = model_asset_path


class FakeMPImage:
    def __init__(self, *, image_format: object, data: object) -> None:
        self.image_format = image_format
        self.data = data


def install_fake_mediapipe(monkeypatch: pytest.MonkeyPatch, landmarker: FakeLandmarker) -> SimpleNamespace:
    mp = ModuleType("mediapipe")
    mp.Image = FakeMPImage
    mp.ImageFormat = SimpleNamespace(SRGB="SRGB")

    vision = ModuleType("mediapipe.tasks.python.vision")
    vision.RunningMode = SimpleNamespace(IMAGE="IMAGE", VIDEO="VIDEO", LIVE_STREAM="LIVE_STREAM")
    vision.HandLandmarkerOptions = FakeHandLandmarkerOptions
    factory = SimpleNamespace(last_options=None)

    def create_from_options(options: object) -> FakeLandmarker:
        factory.last_options = options
        return landmarker

    vision.HandLandmarker = SimpleNamespace(create_from_options=create_from_options)

    base_options = ModuleType("mediapipe.tasks.python.core.base_options")
    base_options.BaseOptions = FakeBaseOptions

    core = ModuleType("mediapipe.tasks.python.core")
    core.__path__ = []
    core.base_options = base_options

    python = ModuleType("mediapipe.tasks.python")
    python.__path__ = []
    python.vision = vision
    python.core = core

    tasks = ModuleType("mediapipe.tasks")
    tasks.__path__ = []
    tasks.python = python

    mp.tasks = tasks

    monkeypatch.setitem(sys.modules, "mediapipe", mp)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks", tasks)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python", python)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python.vision", vision)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python.core", core)
    monkeypatch.setitem(sys.modules, "mediapipe.tasks.python.core.base_options", base_options)

    return SimpleNamespace(mp=mp, vision=vision, base_options=base_options, factory=factory)


class FakeCV2(ModuleType):
    COLOR_BGR2RGB = 1

    def __init__(self) -> None:
        super().__init__("cv2")
        self.cvtcolor_calls: list[tuple[object, int]] = []

    def cvtColor(self, frame_bgr: object, code: int) -> object:
        self.cvtcolor_calls.append((frame_bgr, code))
        return ["rgb", frame_bgr]


def _build_hand_landmarks() -> list[FakeLandmark]:
    return [FakeLandmark(i / 10.0, i / 20.0) for i in range(21)]


def test_video_mode_processes_valid_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    result = FakeResult(
        hand_landmarks=[_build_hand_landmarks()],
        handedness=[[FakeClassification("Right", 0.91)]],
    )
    landmarker = FakeLandmarker(result)
    fake_mp = install_fake_mediapipe(monkeypatch, landmarker)
    fake_cv2 = FakeCV2()
    monkeypatch.setitem(sys.modules, "cv2", fake_cv2)

    tracker = HandTracker(model_path="/tmp/hand_landmarker.task")
    assert fake_mp.factory.last_options.kwargs["running_mode"] == fake_mp.vision.RunningMode.VIDEO
    assert fake_mp.factory.last_options.kwargs["num_hands"] == 1
    assert fake_mp.factory.last_options.kwargs["min_hand_detection_confidence"] == 0.5
    assert fake_mp.factory.last_options.kwargs["min_hand_presence_confidence"] == 0.5
    assert fake_mp.factory.last_options.kwargs["min_tracking_confidence"] == 0.5
    output = tracker.process([[1, 2], [3, 4]], 12345)

    assert len(landmarker.calls) == 1
    assert landmarker.calls[0][1] == 12345
    assert landmarker.calls[0][0].image_format == fake_mp.mp.ImageFormat.SRGB
    assert landmarker.calls[0][0].data == ["rgb", [[1, 2], [3, 4]]]
    assert fake_cv2.cvtcolor_calls == [([[1, 2], [3, 4]], fake_cv2.COLOR_BGR2RGB)]
    assert tracker._landmarker is landmarker
    assert tracker._landmarker.result is result

    assert output.handedness_label == "Right"
    assert output.handedness_confidence == pytest.approx(0.91)
    assert output.thumb_tip == output.landmarks[4]
    assert output.index_tip == output.landmarks[8]
    assert output.landmarks[4].x == pytest.approx(0.4)
    assert output.landmarks[4].y == pytest.approx(0.2)
    assert output.raw_landmarks is result.hand_landmarks[0]


def test_video_mode_returns_empty_when_no_hand(monkeypatch: pytest.MonkeyPatch) -> None:
    result = FakeResult(hand_landmarks=[], handedness=[])
    landmarker = FakeLandmarker(result)
    fake_mp = install_fake_mediapipe(monkeypatch, landmarker)
    monkeypatch.setitem(sys.modules, "cv2", FakeCV2())

    tracker = HandTracker(model_path="/tmp/hand_landmarker.task")
    output = tracker.process([[9, 9]], 42)

    assert len(landmarker.calls) == 1
    assert landmarker.calls[0][1] == 42
    assert landmarker.calls[0][0].image_format == fake_mp.mp.ImageFormat.SRGB
    assert landmarker.calls[0][0].data == ["rgb", [[9, 9]]]
    assert output.landmarks == []
    assert output.thumb_tip is None
    assert output.index_tip is None
    assert output.raw_landmarks is None
    assert output.handedness_label is None
    assert output.handedness_confidence is None


def test_video_mode_timestamp_monotonic_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    result = FakeResult(
        hand_landmarks=[_build_hand_landmarks()],
        handedness=[[FakeClassification("Left", 0.5)]],
    )
    landmarker = FakeLandmarker(result)
    fake_mp = install_fake_mediapipe(monkeypatch, landmarker)
    monkeypatch.setitem(sys.modules, "cv2", FakeCV2())

    tracker = HandTracker(model_path="/tmp/hand_landmarker.task")

    tracker.process([[0]], 100)
    tracker.process([[0]], 101)

    assert [timestamp for _, timestamp in landmarker.calls] == [100, 101]
