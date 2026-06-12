from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import handmouse.app as app_module
import handmouse.config as config_module
import handmouse.coordinate_mapper as coordinate_mapper
from handmouse.app import _is_palm_facing_camera, _mirror_frame, _run_loop
from handmouse.clutch_input import ClutchSnapshot
from handmouse.config import PolicyConfig
from handmouse.gesture_detector import GestureState
from handmouse.hand_tracker import HandTrackingResult
from handmouse.mouse_controller import MouseFailsafeTriggered
from handmouse.interlock import InteractionInterlock
from handmouse.move_mode import MoveModeResult, MoveModeState
from handmouse.policy.gesture_policy import GestureCandidate, RiskClass
from handmouse.tracking.observation import Point3, TrackingQuality
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
        self.update_calls: list[tuple[object, int]] = []
        self.reset_calls = 0
        self.last_velocity = None
        self.last_gain = None
        self.last_depth_factor = None
        self.last_hand_scale = None
        self.state = SimpleNamespace(name="IDLE")

    def update(self, hand_result: object, now_ms: int) -> object:
        self.update_calls.append((hand_result, now_ms))
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

    def update(
        self,
        obs: object,
        now_ms: int,
        point: object,
        palm_open: bool = False,
        generic_pose_active: bool = False,
    ) -> object:
        self.update_calls.append((obs, now_ms, point, palm_open, generic_pose_active))
        assert self.results, "no shortcut results left"
        return self.results.pop(0)

    def reset(self) -> None:
        self.reset_calls += 1


class FakeAltTabDetector:
    def __init__(self, results: list[object]) -> None:
        self.results = list(results)
        self.update_calls: list[tuple[object, int]] = []
        self.reset_calls = 0

    def update(self, landmarks: object, now_ms: int) -> object:
        self.update_calls.append((landmarks, now_ms))
        assert self.results, "no alt-tab results left"
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
        self.telemetries: list[object] = []

    def draw(self, frame: object, hand_result: object, gesture_result: object, is_active: bool, telemetry: object) -> object:
        self.last_telemetry = telemetry
        self.telemetries.append(telemetry)
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


class FakeQualityGate:
    def __init__(self, quality: TrackingQuality) -> None:
        self.quality = quality
        self.calls: list[tuple[object, int, int]] = []

    def update(self, obs: object, screen_width: int, screen_height: int) -> TrackingQuality:
        self.calls.append((obs, screen_width, screen_height))
        return self.quality


class FakeActionRouter:
    def __init__(self, results: list[list[object]]) -> None:
        self.results = list(results)
        self.calls: list[list[object]] = []

    def dispatch(self, intents: list[object], _: object) -> list[object]:
        self.calls.append(intents)
        assert self.results, "no dispatch results left"
        return self.results.pop(0)


class FakePolicy:
    def __init__(self, *, high_risk_cooldown_ms: int = 0, explicit_confirm_required: bool = False) -> None:
        self.high_risk_cooldown_ms = high_risk_cooldown_ms
        self.explicit_confirm_required = explicit_confirm_required

    def evaluate(self, obs: object, quality: object, candidates: list[object], session_state: dict[str, object]) -> list[object]:
        return []


class FakeBuffer:
    def __init__(self, item: tuple[object, object, int]) -> None:
        self.item = item
        self._first = True

    def wait_new_result(self, timeout: float) -> bool:
        if self._first:
            self._first = False
            return True
        return False

    def clear(self) -> None:
        return None

    def get(self) -> tuple[object, object, int]:
        return self.item


class FakeInferenceWorker:
    def __init__(self, item: tuple[object, object, int]) -> None:
        self.buffer = FakeBuffer(item)


class FakeCameraReader:
    pass


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
        landmarks[5] = FramePoint(0.35, 0.6)
        landmarks[17] = FramePoint(0.65, 0.6)
    else:
        landmarks[5] = FramePoint(0.65, 0.6)
        landmarks[17] = FramePoint(0.35, 0.6)
    landmarks[4] = FramePoint(landmarks[5].x, 0.45)
    landmarks[8] = FramePoint(landmarks[5].x, 0.35)
    landmarks[12] = FramePoint(0.5, 0.35)
    landmarks[16] = FramePoint(landmarks[17].x, 0.35)
    landmarks[20] = FramePoint(landmarks[17].x, 0.45)
    return landmarks


def make_back_of_hand_landmarks(*, handedness: str) -> list[FramePoint]:
    landmarks = [FramePoint(0.5, 0.5)] * 21
    landmarks[0] = FramePoint(0.5, 0.8)
    landmarks[9] = FramePoint(0.5, 0.55)
    if handedness == "Left":
        landmarks[5] = FramePoint(0.65, 0.6)
        landmarks[17] = FramePoint(0.35, 0.6)
    else:
        landmarks[5] = FramePoint(0.35, 0.6)
        landmarks[17] = FramePoint(0.65, 0.6)
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
    assert frame_samples[0]["schema_version"] == 2
    assert frame_samples[0]["quality_score"] > 0.0
    assert frame_samples[0]["landmarks"][8] == pytest.approx(
        [landmarks[8].x, landmarks[8].y, raw_landmarks[8].z]
    )
    assert frame_samples[0]["world_landmarks"][8] == pytest.approx(
        [world_landmarks[8].x, world_landmarks[8].y, world_landmarks[8].z]
    )
    assert frame_samples[0]["handedness_label"] == "Left"
    assert frame_samples[0]["handedness_confidence"] == pytest.approx(0.99)
    assert frame_samples[0]["input_is_mirrored"] is config_module.ACTIVE_CONFIG.camera.input_is_mirrored


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


def test_back_of_left_hand_is_rejected() -> None:
    assert _is_palm_facing_camera(make_back_of_hand_landmarks(handedness="Left"), "Left") is False


def test_back_of_right_hand_is_rejected() -> None:
    assert _is_palm_facing_camera(make_back_of_hand_landmarks(handedness="Right"), "Right") is False


def test_run_loop_logs_quality_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    landmarks = make_palm_facing_landmarks(handedness="Left")
    hand_result = SimpleNamespace(
        landmarks=landmarks,
        thumb_tip=landmarks[4],
        index_tip=landmarks[8],
        raw_landmarks=[SimpleNamespace(x=lm.x, y=lm.y, z=0.0) for lm in landmarks],
        world_landmarks=None,
        handedness_label="Left",
        handedness_confidence=0.99,
    )
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
        gesture=FakeGesture([[
            GestureCandidate("test", "task_view", "fire", 1.0, RiskClass.HIGH, True),
        ]]),
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
        quality_gate=FakeQualityGate(
            TrackingQuality(
                ok=False,
                score=0.4,
                reasons=("unstable",),
                palm_span_px=120.0,
                handedness_ok=True,
                stable_frames=1,
                lost_frames=0,
            )
        ),
    )

    decisions = [payload for event_name, payload in events if event_name == "gesture_decision"]
    assert decisions
    assert decisions[0]["quality_reasons"] == ["unstable"]


def test_run_loop_uses_camera_frame_size_for_quality_gate() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    quality_gate = FakeQualityGate(
        TrackingQuality(
            ok=True,
            score=1.0,
            reasons=(),
            palm_span_px=120.0,
            handedness_ok=True,
            stable_frames=4,
            lost_frames=0,
        )
    )
    frame = SimpleNamespace(shape=(480, 640, 3))

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[frame, frame]),
        tracker=FakeTracker([make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[])] * 2),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=FakeShortcutDetector([[]]),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=False, state="IDLE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        quality_gate=quality_gate,
    )

    assert quality_gate.calls
    assert quality_gate.calls[0][1:] == (640, 480)


def test_run_loop_resets_dispatches_when_next_frame_has_no_candidates() -> None:
    cv2 = FakeCv2(wait_keys=[0, 0, ord("q")])
    debug_view = FakeDebugView()
    router = FakeActionRouter([[SimpleNamespace(action="click_left", executed=True)]])

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object(), object()]),
        tracker=FakeTracker([make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[])] * 3),
        pointer=FakePointer(updates=[ScreenDelta(0, 0), ScreenDelta(0, 0)]),
        gesture=FakeGesture(
            [
                [GestureCandidate("test", "click_left", "fire", 1.0, RiskClass.MEDIUM, True)],
                [],
            ]
        ),
        grab_scroll=FakeGrabScroll([[], []]),
        shortcut_detector=FakeShortcutDetector([[], []]),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=True, state="ACTIVE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=debug_view,
        interlock=InteractionInterlock(),
        action_router=router,
    )

    assert len(debug_view.telemetries) >= 2
    assert debug_view.telemetries[0].dispatches
    assert debug_view.telemetries[1].dispatches == []


def test_run_loop_syncs_policy_settings_from_active_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    original_config = config_module.ACTIVE_CONFIG
    monkeypatch.setattr(
        config_module,
        "ACTIVE_CONFIG",
        original_config.__class__(
            camera=original_config.camera,
            pointer=original_config.pointer,
            shortcut=original_config.shortcut,
            clutch=original_config.clutch,
            schema_version=original_config.schema_version,
            policy=PolicyConfig(high_risk_cooldown_ms=321, explicit_confirm_required=True),
            gesture_switches=original_config.gesture_switches,
            gesture_config=original_config.gesture_config,
            grab_scroll_config=original_config.grab_scroll_config,
            view=original_config.view,
            show_osd=original_config.show_osd,
        ),
    )
    policy = FakePolicy(high_risk_cooldown_ms=0, explicit_confirm_required=False)

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([make_hand_result(index_tip=None, landmarks=[])] * 2),
        pointer=FakePointer(updates=[]),
        gesture=FakeGesture([[], []]),
        grab_scroll=FakeGrabScroll([[], []]),
        shortcut_detector=FakeShortcutDetector([[], []]),
        engagement=FakeEngagement(
            [
                make_engagement_result(active=False, state="IDLE"),
                make_engagement_result(active=False, state="IDLE", reason="escape"),
            ]
        ),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        policy=policy,
    )

    assert policy.high_risk_cooldown_ms == 321
    assert policy.explicit_confirm_required is True


def test_run_loop_mirrors_pointer_input_when_preview_is_mirrored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    original_config = config_module.ACTIVE_CONFIG
    monkeypatch.setattr(
        config_module,
        "ACTIVE_CONFIG",
        original_config.__class__(
            camera=original_config.camera,
            pointer=original_config.pointer,
            shortcut=original_config.shortcut,
            clutch=original_config.clutch,
            schema_version=original_config.schema_version,
            policy=original_config.policy,
            gesture_switches=original_config.gesture_switches,
            gesture_config=original_config.gesture_config,
            grab_scroll_config=original_config.grab_scroll_config,
            view=original_config.view.__class__(render_mirrored=True),
            show_osd=original_config.show_osd,
        ),
    )
    pointer = FakePointer(updates=[ScreenDelta(0, 0)])
    landmarks = make_palm_facing_landmarks(handedness="Right")
    hand_result = SimpleNamespace(
        landmarks=landmarks,
        thumb_tip=landmarks[4],
        index_tip=landmarks[8],
        raw_landmarks=None,
        world_landmarks=None,
        handedness_label="Right",
        handedness_confidence=0.99,
    )

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=pointer,
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
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
    )

    mirrored_hand_result, _ = pointer.update_calls[0]
    assert mirrored_hand_result.index_tip is not None
    assert mirrored_hand_result.index_tip.x == pytest.approx(1.0 - hand_result.index_tip.x)
    assert mirrored_hand_result.index_tip.y == pytest.approx(hand_result.index_tip.y)


def test_run_loop_does_not_move_pointer_during_pinch_hold_before_drag_dispatch() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    pointer = FakePointer(updates=[])
    gesture = FakeGesture([[]])
    gesture._left_state = GestureState.PINCH_HOLD
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_palm_facing_landmarks(handedness="Right"))

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=pointer,
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

    assert pointer.update_calls == []


def test_run_loop_suppresses_task_view_detector_while_move_mode_active() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    alt_tab = FakeAltTabDetector([[GestureCandidate("task_view", "task_view", "fire", 1.0, RiskClass.HIGH, True)]])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_palm_facing_landmarks(handedness="Right"))

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
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
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        alt_tab_detector=alt_tab,
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

    assert alt_tab.update_calls == []
    assert alt_tab.reset_calls >= 1


def test_run_loop_resets_task_view_detector_when_open_is_blocked() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    alt_tab = FakeAltTabDetector([[GestureCandidate("task_view", "task_view", "fire", 1.0, RiskClass.HIGH, True)]])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_palm_facing_landmarks(handedness="Right"))
    hand_result.handedness_label = "Right"

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
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
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        alt_tab_detector=alt_tab,
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=False), ClutchSnapshot(clutch_down=False)]),
        move_mode=FakeMoveMode(
            [
                make_move_mode_result(
                    state=MoveModeState.NEUTRAL,
                    movement_enabled=False,
                    move_pose=False,
                    clutch_down=False,
                ),
            ]
        ),
    )

    assert alt_tab.update_calls != []
    assert alt_tab.reset_calls >= 1


def test_run_loop_uses_palm_center_for_shortcut_detection() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    shortcut_detector = FakeShortcutDetector([[]])
    landmarks = make_palm_facing_landmarks(handedness="Right")
    hand_result = make_hand_result(index_tip=FramePoint(0.9, 0.1), landmarks=landmarks)
    hand_result.handedness_label = "Right"

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=shortcut_detector,
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
        clutch_input=FakeClutchInput([ClutchSnapshot(clutch_down=False), ClutchSnapshot(clutch_down=False)]),
        move_mode=FakeMoveMode(
            [
                make_move_mode_result(
                    state=MoveModeState.NEUTRAL,
                    movement_enabled=False,
                    move_pose=False,
                    clutch_down=False,
                ),
            ]
        ),
    )

    _, _, shortcut_point, _, generic_pose_active = shortcut_detector.update_calls[0]
    assert shortcut_point is not None
    assert shortcut_point.x == pytest.approx(0.5)
    assert shortcut_point.y == pytest.approx(0.61)
    assert generic_pose_active is False


def test_run_loop_suppresses_shortcut_detector_while_move_mode_active() -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    shortcut_detector = FakeShortcutDetector([[GestureCandidate("shortcut", "swipe_up", "fire", 1.0, RiskClass.MEDIUM, True)]])
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=make_palm_facing_landmarks(handedness="Right"))

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[object(), object()]),
        tracker=FakeTracker([hand_result, hand_result]),
        pointer=FakePointer(updates=[ScreenDelta(0, 0)]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=shortcut_detector,
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

    assert shortcut_detector.update_calls == []
    assert shortcut_detector.reset_calls >= 1


def test_run_loop_unifies_threaded_result_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cv2 = FakeCv2(wait_keys=[0, ord("q")])
    frame = SimpleNamespace(shape=(480, 640, 3))
    hand_result = make_hand_result(index_tip=FramePoint(0.5, 0.5), landmarks=[])
    unify_calls: list[tuple[object, bool]] = []

    monkeypatch.setattr(
        coordinate_mapper,
        "unify_hand_result",
        lambda raw_result, input_is_mirrored: unify_calls.append((raw_result, input_is_mirrored)) or raw_result,
    )

    _run_loop(
        cv2=cv2,
        camera=FakeCamera(frames=[]),
        tracker=FakeTracker([]),
        pointer=FakePointer(updates=[]),
        gesture=FakeGesture([[]]),
        grab_scroll=FakeGrabScroll([[]]),
        shortcut_detector=FakeShortcutDetector([[]]),
        engagement=FakeEngagement([make_engagement_result(active=False, state="IDLE")]),
        mouse=FakeMouse(),
        shortcut=FakeShortcutController(),
        debug_view=FakeDebugView(),
        interlock=InteractionInterlock(),
        camera_reader=FakeCameraReader(),
        inference_worker=FakeInferenceWorker((hand_result, frame, 1000)),
    )

    assert len(unify_calls) == 1


def test_build_frame_sample_schema_contains_world_z_and_quality() -> None:
    from handmouse.telemetry.schema import build_frame_sample

    payload = build_frame_sample(
        ts_ms=1000,
        frame_age_ms=12,
        pointer_dx=0.0,
        pointer_dy=0.0,
        landmarks=[[0.5, 0.5, 0.01]],
        world_landmarks=[[0.1, 0.2, 0.3]],
        quality_score=0.91,
        quality_reasons=("stable",),
        handedness_label="Right",
        handedness_confidence=0.88,
        input_is_mirrored=True,
    )

    assert payload["schema_version"] == 2
    assert payload["world_landmarks"][0] == [0.1, 0.2, 0.3]
    assert payload["quality_score"] == 0.91
    assert payload["handedness_label"] == "Right"
    assert payload["handedness_confidence"] == pytest.approx(0.88)
    assert payload["input_is_mirrored"] is True


def test_coordinate_mapper_preserves_physical_handedness_and_world_landmarks() -> None:
    world_landmarks = [Point3(x=0.1, y=0.2, z=0.3)]
    raw = HandTrackingResult(
        landmarks=[FramePoint(0.25, 0.75)],
        thumb_tip=None,
        index_tip=None,
        raw_landmarks=[SimpleNamespace(x=0.25, y=0.75, z=-0.1)],
        world_landmarks=world_landmarks,
        handedness_label="Right",
        handedness_confidence=0.88,
    )

    unified = coordinate_mapper.unify_hand_result(raw, input_is_mirrored=False)

    assert unified.handedness_label == "Right"
    assert unified.landmarks[0] == FramePoint(0.25, 0.75)
    assert unified.world_landmarks == world_landmarks
