from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import handmouse.app as app_module
from handmouse.app import _mirror_frame, _run_loop
from handmouse.clutch_input import ClutchSnapshot
from handmouse.mouse_controller import MouseFailsafeTriggered
from handmouse.move_mode import MoveModeResult, MoveModeState
from handmouse.pointer_mapper import FramePoint, ScreenDelta


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

    def update(self, thumb: object, index: object, now_ms: int) -> object:
        self.calls.append((thumb, index, now_ms))
        assert self.results, "no gesture results left"
        return self.results.pop(0)

    def reset(self) -> None:
        return None


class FakeGrabScroll:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.reset_calls = 0

    def update(self, landmarks: object, now_ms: int) -> object:
        assert self.results, "no grab results left"
        return self.results.pop(0)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeShortcutDetector:
    def __init__(self) -> None:
        self.reset_calls = 0
        self.update_calls: list[tuple[object, int]] = []

    def update(self, point: object, now_ms: int) -> object:
        self.update_calls.append((point, now_ms))
        return SimpleNamespace(action=None)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeEngagement:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.force_idle_calls = 0

    def update(self, **kwargs: object) -> object:
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
        handedness_label=None,
        handedness_confidence=None,
    )


def make_pose_landmarks(*, grab_like: bool) -> list[FramePoint]:
    points = [FramePoint(0.5, 0.5) for _ in range(21)]
    points[0] = FramePoint(0.5, 0.75)
    points[5] = FramePoint(0.42, 0.58)
    points[9] = FramePoint(0.50, 0.55)
    points[13] = FramePoint(0.58, 0.58)
    points[17] = FramePoint(0.64, 0.64)
    points[4] = FramePoint(0.46, 0.48)
    points[8] = FramePoint(0.49, 0.47)

    if grab_like:
        points[12] = FramePoint(0.53, 0.60)
        points[16] = FramePoint(0.58, 0.63)
        points[20] = FramePoint(0.62, 0.67)
    else:
        points[12] = FramePoint(0.50, 0.34)
        points[16] = FramePoint(0.59, 0.36)
        points[20] = FramePoint(0.68, 0.42)

    return points


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

    monkeypatch.setattr(app_module, "_load_cv2", lambda: DummyCv2())
    monkeypatch.setattr(app_module, "_screen_size", lambda: (1920, 1080))

    def fail_open(self: object) -> None:
        raise RuntimeError("camera open failed")

    monkeypatch.setattr(app_module.Camera, "open", fail_open)

    with pytest.raises(RuntimeError, match="camera open failed"):
        app_module.main()


def test_run_loop_resets_shortcut_detector_when_inactive() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    camera = FakeCamera(frames=[object(), object()])
    tracker = FakeTracker(
        [
            make_hand_result(index_tip=None),
            make_hand_result(index_tip=None),
        ]
    )
    pointer = FakePointer(updates=[])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=None, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="NO_HAND"), active=False, scroll_delta=0, is_grab_pose=False),
        ]
    )
    shortcut_detector = FakeShortcutDetector()
    engagement = FakeEngagement(
        [
            make_engagement_result(active=False, state="IDLE", reason="idle"),
            make_engagement_result(active=False, state="IDLE", reason="escape"),
        ]
    )
    mouse = FakeMouse()
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
    )

    assert shortcut_detector.reset_calls == 1


def test_run_loop_resets_shortcut_detector_when_grab_pose_blocks_swipe() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[FramePoint(0.0, 0.0)] * 21)
    camera = FakeCamera(frames=[object(), object()])
    tracker = FakeTracker([hand_result, hand_result])
    pointer = FakePointer(updates=[None])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=0.1, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="GRABBING"), active=False, scroll_delta=0, is_grab_pose=True),
        ]
    )
    shortcut_detector = FakeShortcutDetector()
    engagement = FakeEngagement(
        [
            make_engagement_result(active=True, state="ACTIVE"),
            make_engagement_result(active=False, state="IDLE", reason="escape"),
        ]
    )

    _run_loop(
        cv2=cv2,
        camera=camera,
        tracker=tracker,
        pointer=pointer,
        gesture=gesture,
        grab_scroll=grab_scroll,
        shortcut_detector=shortcut_detector,
        engagement=engagement,
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
    )

    assert shortcut_detector.reset_calls == 1
    assert shortcut_detector.update_calls == []


def test_run_loop_aborts_cleanly_on_mouse_failsafe() -> None:
    cv2 = FakeCv2(wait_keys=[0])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[FramePoint(0.0, 0.0)] * 21)
    camera = FakeCamera(frames=[object()])
    tracker = FakeTracker([hand_result])
    pointer = FakePointer(updates=[ScreenDelta(10, 0)])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=0.1, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="NO_HAND"), active=False, scroll_delta=0, is_grab_pose=False),
        ]
    )
    shortcut_detector = FakeShortcutDetector()
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
    )

    assert engagement.force_idle_calls == 1
    assert mouse.control_enabled[-1] is False
    assert shortcut.enabled[-1] is False


def test_run_loop_suppresses_pinch_when_hand_pose_is_grab_like() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    landmarks = make_pose_landmarks(grab_like=True)
    hand_result = SimpleNamespace(
        landmarks=landmarks,
        thumb_tip=landmarks[4],
        index_tip=landmarks[8],
        raw_landmarks=None,
        handedness_label=None,
        handedness_confidence=None,
    )
    camera = FakeCamera(frames=[object(), object()])
    tracker = FakeTracker([hand_result, hand_result])
    pointer = FakePointer(updates=[None])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=None, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="RELEASED"), active=False, scroll_delta=0, is_grab_pose=False),
        ]
    )
    shortcut_detector = FakeShortcutDetector()
    engagement = FakeEngagement(
        [
            make_engagement_result(active=True, state="ACTIVE"),
            make_engagement_result(active=False, state="IDLE", reason="escape"),
        ]
    )

    _run_loop(
        cv2=cv2,
        camera=camera,
        tracker=tracker,
        pointer=pointer,
        gesture=gesture,
        grab_scroll=grab_scroll,
        shortcut_detector=shortcut_detector,
        engagement=engagement,
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
    )

    assert gesture.calls[0][0] is None
    assert gesture.calls[0][1] is None


def test_run_loop_moves_only_when_clutch_down_and_mode_active() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_pose_landmarks(grab_like=False))
    camera = FakeCamera(frames=[object(), object()])
    tracker = FakeTracker([hand_result, hand_result])
    pointer = FakePointer(updates=[ScreenDelta(12, 0)])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=None, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="NO_HAND"), active=False, scroll_delta=0, is_grab_pose=False),
        ]
    )
    shortcut_detector = FakeShortcutDetector()
    engagement = FakeEngagement(
        [
            make_engagement_result(active=True, state="ACTIVE"),
            make_engagement_result(active=False, state="IDLE", reason="escape"),
        ]
    )
    clutch_input = FakeClutchInput([ClutchSnapshot(clutch_down=True)])
    move_mode = FakeMoveMode(
        [
            make_move_mode_result(
                state=MoveModeState.ACTIVE,
                movement_enabled=True,
                move_pose=True,
                clutch_down=True,
            ),
        ]
    )
    mouse = FakeMouse()

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
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        clutch_input=clutch_input,
        move_mode=move_mode,
    )

    assert mouse.moves == [ScreenDelta(12, 0)]


def test_run_loop_blocks_click_and_scroll_while_move_mode_active() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_pose_landmarks(grab_like=False))
    camera = FakeCamera(frames=[object(), object()])
    tracker = FakeTracker([hand_result, hand_result])
    pointer = FakePointer(updates=[ScreenDelta(12, 0)])
    gesture = FakeGesture(
        [
            SimpleNamespace(should_click=False, pinch_distance=None, state=SimpleNamespace(name="PINCH_OPEN")),
        ]
    )
    grab_scroll = FakeGrabScroll(
        [
            SimpleNamespace(state=SimpleNamespace(name="DRAGGING"), active=True, scroll_delta=9, is_grab_pose=True),
        ]
    )
    shortcut = FakeShortcutController()

    _run_loop(
        cv2=cv2,
        camera=camera,
        tracker=tracker,
        pointer=pointer,
        gesture=gesture,
        grab_scroll=grab_scroll,
        shortcut_detector=FakeShortcutDetector(),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=shortcut,
        debug_view=FakeDebugView(),
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=True)]),
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

    assert shortcut.scrolled == []
    assert gesture.calls[0][0] is None
    assert gesture.calls[0][1] is None


def test_run_loop_passes_clutch_and_move_mode_telemetry() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_pose_landmarks(grab_like=False))
    debug_view = FakeDebugView()

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(12, 0)]),
        gesture=FakeGesture(
            [
                SimpleNamespace(should_click=False, pinch_distance=None, state=SimpleNamespace(name="PINCH_OPEN")),
            ]
        ),
        grab_scroll=FakeGrabScroll(
            [
                SimpleNamespace(state=SimpleNamespace(name="NO_HAND"), active=False, scroll_delta=0, is_grab_pose=False),
            ]
        ),
        shortcut_detector=FakeShortcutDetector(),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=debug_view,
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=True)]),
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
    assert debug_view.last_telemetry.move_pose is True
