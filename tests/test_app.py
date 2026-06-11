from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import handmouse.app as app_module
from handmouse.app import _is_palm_facing_camera, _mirror_frame, _run_loop
from handmouse.clutch_input import ClutchSnapshot
from handmouse.mouse_controller import MouseFailsafeTriggered
from handmouse.interlock import InteractionInterlock
from handmouse.move_mode import MoveModeResult, MoveModeState
from handmouse.tracking.observation import Point3
from handmouse.types import FramePoint, ScreenDelta


class FakeCv2:
    def __init__(self, wait_keys: list[int] | None = None) -> None:
        self.calls: list[tuple[object, int]] = []
        self.wait_keys = wait_keys or []
        self.imshow_calls: list[tuple[str, object]] = []

    def flip(self, frame: object, flip_code: int) -> object:
        self.calls.append((frame, flip_code))
        return ("mirrored", frame, flip_code)

    def waitKey(self, delay: int) -> int:
        if self.wait_keys:
            return self.wait_keys.pop(0)
        return 0

    def imshow(self, name: str, frame: object) -> None:
        self.imshow_calls.append((name, frame))


@dataclass
class FakeCamera:
    frames: list[object]
    backend_name: str = "CAP_DSHOW"

    def read(self) -> tuple[bool, object]:
        if not self.frames:
            return False, None
        return True, self.frames.pop(0)


class FakeTracker:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)

    def process(self, frame: object, frame_timestamp_ms: int | None = None) -> object:
        assert self.results, "no tracker results left"
        return self.results.pop(0)


class FakePointer:
    def __init__(self, updates: list[object]) -> None:
        self.updates = list(updates)
        self.reset_calls = 0
        self.last_velocity = None
        self.last_gain = None
        self.last_depth_factor = None
        self.last_hand_scale = None
        self.state = SimpleNamespace(name="IDLE")

    def update(self, hand_result: object, now_ms: int) -> object:
        assert self.updates, "no pointer updates left"
        return self.updates.pop(0)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeGesture:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.calls: list[tuple[object, object, int]] = []

    def update(self, obs, now_ms: int) -> object:
        self.calls.append((obs, now_ms))
        assert self.results, "no gesture results left"
        return self.results.pop(0)

    def reset(self) -> None:
        return None


class FakeGrabScroll:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.reset_calls = 0

    def update(self, obs: object, now_ms: int) -> object:
        assert self.results, "no grab results left"
        return self.results.pop(0)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeShortcutDetector:
    def __init__(self, results: list[object]) -> None:
        self.reset_calls = 0
        self.results = list(results)
        self.update_calls: list[tuple[object, int]] = []

    def update(self, obs: object, now_ms: int, point: object, palm_open: bool = False) -> object:
        self.update_calls.append((obs, now_ms, point, palm_open))
        assert self.results, "no shortcut results left"
        return self.results.pop(0)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeEngagement:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.force_idle_calls = 0
        self.calls: list[dict[str, object]] = []

    def update(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        assert self.results, "no engagement results left"
        return self.results.pop(0)

    def force_idle(self) -> None:
        self.force_idle_calls += 1


class FakeMouse:
    def __init__(self, *, move_exception: Exception | None = None) -> None:
        self.control_enabled: list[bool] = []
        self.move_exception = move_exception
        self.moves: list[object] = []
        self.clicks = 0

    def set_control_enabled(self, enabled: bool) -> None:
        self.control_enabled.append(enabled)

    def move_relative(self, delta: object) -> None:
        self.moves.append(delta)
        if self.move_exception is not None:
            raise self.move_exception

    def left_click(self) -> None:
        self.clicks += 1


class FakeShortcutController:
    def __init__(self) -> None:
        self.enabled: list[bool] = []
        self.executed: list[object] = []
        self.scrolled: list[int] = []

    def set_enabled(self, enabled: bool) -> None:
        self.enabled.append(enabled)

    def execute(self, action: object) -> None:
        self.executed.append(action)

    def scroll(self, amount: int) -> None:
        self.scrolled.append(amount)


class FakeDebugView:
    def __init__(self) -> None:
        self.last_telemetry: object | None = None

    def draw(self, frame: object, hand_result: object, gesture_result: object, is_active: bool, telemetry: object) -> object:
        self.last_telemetry = telemetry
        return frame


class FakeClutchInput:
    def __init__(self, snapshots: list[ClutchSnapshot]) -> None:
        self.snapshots = list(snapshots)
        self.stop_calls = 0

    def snapshot(self) -> ClutchSnapshot:
        assert self.snapshots, "no clutch snapshots left"
        return self.snapshots.pop(0)

    def stop(self) -> None:
        self.stop_calls += 1


class FakeMoveMode:
    def __init__(self, results: list[MoveModeResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[bool, bool, int]] = []

    def update(self, *, clutch_down: bool, move_pose: bool, now_ms: int) -> MoveModeResult:
        self.calls.append((clutch_down, move_pose, now_ms))
        assert self.results, "no move mode results left"
        return self.results.pop(0)


def make_hand_result(*, index_tip: FramePoint | None, landmarks: list[FramePoint] | None = None) -> object:
    return SimpleNamespace(
        landmarks=[] if landmarks is None else landmarks,
        thumb_tip=index_tip,
        index_tip=index_tip,
        raw_landmarks=None,
        world_landmarks=None,
        handedness_label="Left",
        handedness_confidence=0.99,
    )


def make_palm_facing_landmarks(*, handedness: str) -> list[FramePoint]:
    landmarks = [FramePoint(0.5, 0.5)] * 21
    landmarks[0] = FramePoint(0.5, 0.8)
    landmarks[9] = FramePoint(0.5, 0.55)
    if handedness == "Left":
        landmarks[5] = FramePoint(0.65, 0.6)
        landmarks[17] = FramePoint(0.35, 0.6)
    else:
        landmarks[5] = FramePoint(0.35, 0.6)
        landmarks[17] = FramePoint(0.65, 0.6)
    landmarks[4] = FramePoint(landmarks[5].x, 0.45)
    landmarks[8] = FramePoint(landmarks[5].x, 0.35)
    landmarks[12] = FramePoint(0.5, 0.35)
    landmarks[16] = FramePoint(landmarks[17].x, 0.35)
    landmarks[20] = FramePoint(landmarks[17].x, 0.45)
    return landmarks


def make_engagement_result(*, active: bool, state: str, reason: str = "active") -> object:
    return SimpleNamespace(
        is_active=active,
        state=SimpleNamespace(name=state),
        reason=reason,
    )


def make_move_mode_result(
    *,
    state: MoveModeState,
    movement_enabled: bool,
    move_pose: bool,
    clutch_down: bool,
) -> MoveModeResult:
    return MoveModeResult(
        state=state,
        movement_enabled=movement_enabled,
        move_pose=move_pose,
        clutch_down=clutch_down,
    )


def test_mirror_frame_flips_horizontally() -> None:
    cv2 = FakeCv2()
    frame = object()

    result = _mirror_frame(cv2, frame)

    assert result == ("mirrored", frame, 1)
    assert cv2.calls == [(frame, 1)]


def test_main_preserves_startup_error_when_camera_open_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyCv2:
        def destroyAllWindows(self) -> None:
            return None

    monkeypatch.setattr("sys.argv", ["app.py"])
    monkeypatch.setattr(app_module, "_load_cv2", lambda: DummyCv2())
    monkeypatch.setattr(app_module, "_screen_size", lambda: (1920, 1080))

    def fail_open(self: object) -> None:
        raise RuntimeError("camera open failed")

    monkeypatch.setattr(app_module.Camera, "open", fail_open)

    with pytest.raises(RuntimeError, match="camera open failed"):
        app_module.main()


def test_run_loop_aborts_cleanly_on_mouse_failsafe() -> None:
    cv2 = FakeCv2(wait_keys=[0])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[])
    camera = FakeCamera(frames=[object()])
    tracker = FakeTracker([hand_result])
    pointer = FakePointer(updates=[ScreenDelta(10, 0)])
    gesture = FakeGesture([[]])
    grab_scroll = FakeGrabScroll([[]])
    shortcut_detector = FakeShortcutDetector([[]])
    engagement = FakeEngagement([make_engagement_result(active=True, state="ACTIVE")])
    mouse = FakeMouse(move_exception=MouseFailsafeTriggered("corner"))
    shortcut = FakeShortcutController()

    _run_loop(
        cv2=cv2,
        camera=camera,
        tracker=tracker,
        pointer=pointer,
        gesture=gesture,
        grab_scroll=grab_scroll,
        shortcut_detector=shortcut_detector,
        engagement=engagement,
        mouse=mouse,
        shortcut=shortcut,
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
    )

    assert engagement.force_idle_calls == 1
    assert mouse.control_enabled[-1] is False
    assert shortcut.enabled[-1] is False


def test_run_loop_passes_clutch_and_move_mode_telemetry() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[])
    debug_view = FakeDebugView()

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(12, 0)]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=FakeShortcutDetector([[]]),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=debug_view,
        interlock=InteractionInterlock(),
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=True), ClutchSnapshot(clutch_down=True)]),
        move_mode=FakeMoveMode(
            [
                make_move_mode_result(
                    state=MoveModeState.ACTIVE,
                    movement_enabled=True,
                    move_pose=True,
                    clutch_down=True,
                ),
            ]
        ),
    )

    assert debug_view.last_telemetry.clutch_down is True
    assert debug_view.last_telemetry.move_mode == "ACTIVE"


def test_run_loop_preserves_landmark_z_and_logs_world_z(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    landmarks = make_palm_facing_landmarks(handedness="Left")
    raw_landmarks = [SimpleNamespace(x=lm.x, y=lm.y, z=0.01 * idx) for idx, lm in enumerate(landmarks)]
    world_landmarks = [Point3(x=0.1 * idx, y=0.2 * idx, z=0.3 * idx) for idx in range(21)]
    hand_result = SimpleNamespace(
        landmarks=landmarks,
        thumb_tip=landmarks[4],
        index_tip=landmarks[8],
        raw_landmarks=raw_landmarks,
        world_landmarks=world_landmarks,
        handedness_label="Left",
        handedness_confidence=0.99,
    )
    gesture = FakeGesture([[]])
    events: list[tuple[str, object]] = []
    monkeypatch.setattr(
        "handmouse.telemetry.writer.log_event",
        lambda event_name, payload: events.append((event_name, payload)),
    )

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
        gesture=gesture,
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=FakeShortcutDetector([[]]),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
    )

    obs = gesture.calls[0][0]
    assert obs.image_landmarks[8].z == pytest.approx(raw_landmarks[8].z)
    frame_samples = [payload for event_name, payload in events if event_name == "frame_sample"]
    assert frame_samples
    assert frame_samples[0]["world_landmarks"][8] == pytest.approx(
        [world_landmarks[8].x, world_landmarks[8].y, world_landmarks[8].z]
    )


def test_run_loop_does_not_mask_missing_hand_when_clutch_is_down() -> None:
    cv2 = FakeCv2(wait_keys=[ord("q")])
    engagement = FakeEngagement([make_engagement_result(active=False, state="IDLE", reason="escape")])

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object()]),
        tracker=FakeTracker([make_hand_result(index_tip=None, landmarks=[])]),
        pointer=FakePointer(updates=[]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=FakeShortcutDetector([[]]),
        engagement=engagement,
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=True)]),
    )

    assert engagement.calls[0]["hand_missing"] is True


def test_palm_facing_left_hand_matches_cross_sign_comment() -> None:
    assert _is_palm_facing_camera(make_palm_facing_landmarks(handedness="Left"), "Left") is True


def test_palm_facing_right_hand_matches_cross_sign_comment() -> None:
    assert _is_palm_facing_camera(make_palm_facing_landmarks(handedness="Right"), "Right") is True
