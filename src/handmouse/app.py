from __future__ import annotations

import time
from typing import Any

from handmouse.camera import Camera
from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugTelemetry, DebugView
from handmouse.engagement import EngagementConfig, EngagementFSM
from handmouse.gesture_detector import GestureConfig, GestureDetector
from handmouse.grab_scroll_detector import GrabScrollConfig, GrabScrollDetector
from handmouse.hand_tracker import HandTracker
from handmouse.mouse_controller import MouseController
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
        mouse = MouseController()
        shortcut = ShortcutController()
        debug_view = DebugView(config)

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
        )
    finally:
        mouse.set_control_enabled(False)
        shortcut.set_enabled(False)
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

        if is_active:
            delta = pointer.update(hand_result, now_ms)
            if delta is not None and (delta.dx != 0 or delta.dy != 0):
                mouse.move_relative(delta)

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

        grab_result = grab_scroll.update(hand_result.landmarks, now_ms)
        if is_active and grab_result.scroll_delta != 0:
            shortcut.scroll(grab_result.scroll_delta)

        if (
            is_active
            and hand_result.index_tip is not None
            and not grab_result.is_grab_pose
        ):
            shortcut_result = shortcut_detector.update(hand_result.index_tip, now_ms)
            if shortcut_result.action is not None:
                shortcut.execute(shortcut_result.action)

        telemetry = DebugTelemetry(
            fps=fps,
            frame_age_ms=frame_age_ms,
            backend_name=camera.backend_name,
            pointer=pointer,
            engagement=engagement_result,
            grab_scroll=grab_result,
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


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


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
