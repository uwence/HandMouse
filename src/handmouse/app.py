from __future__ import annotations

import time
from typing import Any

from handmouse.camera import Camera
from handmouse.clutch_input import ClutchSnapshot, GlobalClutchInput
from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugTelemetry, DebugView
from handmouse.engagement import EngagementConfig, EngagementFSM
from handmouse.gesture_detector import GestureConfig, GestureDetector
from handmouse.grab_scroll_detector import (
    GrabScrollConfig,
    GrabScrollDetector,
    GrabScrollResult,
    GrabScrollState,
)
from handmouse.hand_tracker import HandTracker
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.move_mode import (
    MoveModeConfig,
    MoveModeController,
    MoveModeResult,
    MoveModeState,
)
from handmouse.pointer_engine import PointerEngine, PointerEngineConfig
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutDetector


WINDOW_NAME = "HandMouse"


def main() -> None:
    config = DEFAULT_CONFIG
    cv2 = _load_cv2()
    screen_size = _screen_size()
    if screen_size is None:
        screen_w, screen_h = 1920, 1080
    else:
        screen_w, screen_h = screen_size

    camera = Camera(config.camera)
    tracker: HandTracker | None = None
    mouse = MouseController()
    shortcut = ShortcutController()
    clutch_input = GlobalClutchInput()

    try:
        camera.open()
        tracker = HandTracker(num_hands=1)

        pointer = PointerEngine(
            PointerEngineConfig(
                screen_width=screen_w,
                screen_height=screen_h,
                control_region=config.pointer.control_region,
            )
        )
        gesture = GestureDetector(GestureConfig())
        grab_scroll = GrabScrollDetector(GrabScrollConfig())
        shortcut_detector = ShortcutDetector(config.shortcut)
        engagement = EngagementFSM(EngagementConfig())
        move_mode = MoveModeController(MoveModeConfig())
        debug_view = DebugView(config)
        clutch_input.start()

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
            debug_view=debug_view,
            clutch_input=clutch_input,
            move_mode=move_mode,
        )
    finally:
        mouse.set_control_enabled(False)
        shortcut.set_enabled(False)
        clutch_input.stop()
        camera.release()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()


def _run_loop(
    *,
    cv2: Any,
    camera: Camera,
    tracker: HandTracker,
    pointer: PointerEngine,
    gesture: GestureDetector,
    grab_scroll: GrabScrollDetector,
    shortcut_detector: ShortcutDetector,
    engagement: EngagementFSM,
    mouse: MouseController,
    shortcut: ShortcutController,
    debug_view: DebugView,
    clutch_input: Any | None = None,
    move_mode: Any | None = None,
) -> None:
    previous_frame_time = time.perf_counter()
    previous_frame_capture_time = previous_frame_time
    palm_visible_start_ms: int | None = None
    last_m_state = False
    last_q_state = False

    while True:
        ok, frame = camera.read()
        if not ok or frame is None:
            raise RuntimeError(
                "Could not read a frame from the camera. Check Windows camera "
                "permissions, close other apps using the camera, or change the "
                "camera index in DEFAULT_CONFIG."
            )
        frame = _mirror_frame(cv2, frame)

        now = time.perf_counter()
        frame_capture_time = now
        frame_age_ms = int((now - previous_frame_capture_time) * 1000)
        previous_frame_capture_time = frame_capture_time
        now_ms = int(now * 1000)
        fps = _fps(previous_frame_time, now)
        previous_frame_time = now

        hand_result = tracker.process(frame, frame_timestamp_ms=now_ms)
        hand_missing = not hand_result.landmarks

        palm_visible = _is_palm_open(hand_result.landmarks)
        if palm_visible:
            if palm_visible_start_ms is None:
                palm_visible_start_ms = now_ms
            palm_hold_ms = now_ms - palm_visible_start_ms
        else:
            palm_visible_start_ms = None
            palm_hold_ms = 0

        raw_key = cv2.waitKey(1) & 0xFF
        m_pressed_edge = _is_key_pressed_edge(raw_key, ord("m"), last_m_state)
        q_pressed_edge = _is_key_pressed_edge(raw_key, ord("q"), last_q_state)
        last_m_state = raw_key == ord("m")
        last_q_state = raw_key == ord("q")

        engagement_result = engagement.update(
            hotkey_pressed=m_pressed_edge,
            palm_visible=palm_visible,
            palm_hold_ms=palm_hold_ms,
            hand_missing=hand_missing,
            escape_requested=q_pressed_edge,
            now_ms=now_ms,
        )

        if q_pressed_edge:
            break

        is_active = engagement_result.is_active
        mouse.set_control_enabled(is_active)
        shortcut.set_enabled(is_active)
        clutch_snapshot = _clutch_snapshot(clutch_input)
        move_pose = _is_move_pose(hand_result.landmarks)
        move_mode_result = _move_mode_result(
            move_mode=move_mode,
            is_active=is_active,
            clutch_down=clutch_snapshot.clutch_down,
            move_pose=move_pose,
            now_ms=now_ms,
        )
        move_active = is_active and move_mode_result.movement_enabled
        shortcut_should_reset = False

        try:
            if move_active:
                delta = pointer.update(hand_result, now_ms)
                if delta is not None and (delta.dx != 0 or delta.dy != 0):
                    mouse.move_relative(delta)
                gesture_result = gesture.update(None, None, now_ms)
                grab_scroll.reset()
                grab_result = _neutral_grab_result()
                shortcut_should_reset = True
            elif is_active and not clutch_snapshot.clutch_down:
                pointer.reset()
                grab_result = grab_scroll.update(hand_result.landmarks, now_ms)
                pinch_suppressed = (
                    grab_result.is_grab_pose
                    or _is_grab_like_hand_pose(hand_result.landmarks)
                )
                if pinch_suppressed:
                    gesture_result = gesture.update(None, None, now_ms)
                else:
                    gesture_result = gesture.update(
                        hand_result.thumb_tip,
                        hand_result.index_tip,
                        now_ms,
                    )
                if gesture_result.should_click:
                    mouse.left_click()
            else:
                gesture_result = gesture.update(None, None, now_ms)
                pointer.reset()
                grab_scroll.reset()
                grab_result = _neutral_grab_result()
                shortcut_should_reset = True
            if is_active and not clutch_snapshot.clutch_down and grab_result.scroll_delta != 0:
                shortcut.scroll(grab_result.scroll_delta)

            if shortcut_should_reset or move_active or clutch_snapshot.clutch_down:
                shortcut_detector.reset()
            elif not is_active or hand_result.index_tip is None or grab_result.is_grab_pose:
                shortcut_detector.reset()
            else:
                shortcut_result = shortcut_detector.update(hand_result.index_tip, now_ms)
                if shortcut_result.action is not None:
                    shortcut.execute(shortcut_result.action)
        except Exception as exc:
            if _is_failsafe_abort(exc):
                _abort_control(
                    mouse=mouse,
                    shortcut=shortcut,
                    engagement=engagement,
                    gesture=gesture,
                    pointer=pointer,
                    shortcut_detector=shortcut_detector,
                )
                break
            raise

        telemetry = DebugTelemetry(
            fps=fps,
            frame_age_ms=frame_age_ms,
            backend_name=camera.backend_name,
            pointer=pointer,
            engagement=engagement_result,
            grab_scroll=grab_result,
            clutch_down=clutch_snapshot.clutch_down,
            move_mode=move_mode_result.state.name,
            move_pose=move_mode_result.move_pose,
        )

        debug_frame = debug_view.draw(
            frame,
            hand_result,
            gesture_result,
            is_active,
            telemetry,
        )

        cv2.imshow(WINDOW_NAME, debug_frame)


def _is_key_pressed_edge(raw_key: int, target: int, last_state: bool) -> bool:
    """Treat any non-zero key match within this frame as a press edge.

    OpenCV waitKey does not expose key-up events, so we approximate a press
    edge with the frame's key. This means holding the key down will fire
    multiple edges across frames; the consumer (EngagementFSM) is responsible
    for handling repeated edges gracefully.
    """

    return raw_key == target and not last_state


def _is_palm_open(landmarks: list[Any] | None) -> bool:
    """Loose open-palm heuristic: 4 fingertips further from palm center than MCPs."""

    if not landmarks or len(landmarks) < 21:
        return False

    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)

    fingertip_indices = (8, 12, 16, 20)
    mcp_indices = (5, 9, 13, 17)
    extended = 0
    for tip_i, mcp_i in zip(fingertip_indices, mcp_indices):
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d > 1.1:
            extended += 1
    return extended >= 3


def _is_move_pose(landmarks: list[Any] | None) -> bool:
    if not landmarks or len(landmarks) < 21:
        return False

    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)

    extended = 0
    for tip_i, mcp_i in ((8, 5), (12, 9)):
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d > 1.2:
            extended += 1

    curled = 0
    for tip_i, mcp_i in ((16, 13), (20, 17)):
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d < 1.35:
            curled += 1

    return extended == 2 and curled >= 1


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _is_grab_like_hand_pose(landmarks: list[Any] | None) -> bool:
    if not landmarks or len(landmarks) < 21:
        return False

    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)
    palm_scale = _dist(wrist.x, wrist.y, middle_mcp.x, middle_mcp.y)
    if palm_scale <= 0:
        return False

    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    thumb_index_ratio = _dist(thumb_tip.x, thumb_tip.y, index_tip.x, index_tip.y) / palm_scale
    if thumb_index_ratio > 1.8:
        return False

    curled = 0
    for mcp_i, tip_i in ((9, 12), (13, 16), (17, 20)):
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d <= 1.85:
            curled += 1
    return curled >= 2


def _screen_size() -> tuple[int, int] | None:
    try:
        import pyautogui
    except Exception:
        return None
    try:
        width, height = pyautogui.size()
        return int(width), int(height)
    except Exception:
        return None


def _abort_control(
    *,
    mouse: MouseController,
    shortcut: ShortcutController,
    engagement: EngagementFSM,
    gesture: GestureDetector,
    pointer: PointerEngine,
    shortcut_detector: ShortcutDetector,
) -> None:
    mouse.set_control_enabled(False)
    shortcut.set_enabled(False)
    engagement.force_idle()
    gesture.reset()
    pointer.reset()
    shortcut_detector.reset()


def _is_failsafe_abort(exc: Exception) -> bool:
    return isinstance(exc, MouseFailsafeTriggered) or exc.__class__.__name__ == "FailSafeException"


def _clutch_snapshot(clutch_input: Any | None) -> ClutchSnapshot:
    if clutch_input is None:
        return ClutchSnapshot(clutch_down=False)
    return clutch_input.snapshot()


def _move_mode_result(
    *,
    move_mode: Any | None,
    is_active: bool,
    clutch_down: bool,
    move_pose: bool,
    now_ms: int,
) -> MoveModeResult:
    if move_mode is None:
        return MoveModeResult(
            state=MoveModeState.ACTIVE if is_active else MoveModeState.NEUTRAL,
            movement_enabled=is_active,
            move_pose=move_pose,
            clutch_down=clutch_down,
        )
    return move_mode.update(
        clutch_down=clutch_down,
        move_pose=move_pose,
        now_ms=now_ms,
    )


def _neutral_grab_result() -> GrabScrollResult:
    return GrabScrollResult(
        state=GrabScrollState.NO_HAND,
        active=False,
        scroll_delta=0,
        displacement_x=None,
        displacement_y=None,
        is_grab_pose=False,
    )


def _fps(previous_time: float, now: float) -> float:
    elapsed = now - previous_time
    if elapsed <= 0:
        return 0.0
    return 1.0 / elapsed


def _mirror_frame(cv2: Any, frame: Any) -> Any:
    return cv2.flip(frame, 1)


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required to run HandMouse. Install opencv-python."
        ) from exc

    return cv2


__all__ = ["main"]


if __name__ == "__main__":
    main()
