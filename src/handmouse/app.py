from __future__ import annotations

import time
from typing import Any

from handmouse.camera import Camera
from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugView
from handmouse.gesture_detector import GestureDetector
from handmouse.hand_tracker import HandTracker
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.pointer_mapper import PointerMapper


WINDOW_NAME = "HandMouse"


def main() -> None:
    config = DEFAULT_CONFIG
    cv2 = _load_cv2()
    mouse = MouseController()
    screen_width, screen_height = _screen_size()

    camera = Camera(config.camera)
    tracker: HandTracker | None = None

    try:
        camera.open()
        tracker = _create_tracker()
        mapper = PointerMapper(screen_width, screen_height, config.pointer)
        detector = GestureDetector(config.gesture)
        debug_view = DebugView(config)

        _run_loop(
            cv2=cv2,
            camera=camera,
            tracker=tracker,
            mapper=mapper,
            detector=detector,
            mouse=mouse,
            debug_view=debug_view,
        )
    finally:
        mouse.set_control_enabled(False)
        camera.release()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()


def _run_loop(
    *,
    cv2: Any,
    camera: Camera,
    tracker: HandTracker,
    mapper: PointerMapper,
    detector: GestureDetector,
    mouse: MouseController,
    debug_view: DebugView,
) -> None:
    previous_frame_time = time.perf_counter()

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
        fps = _fps(previous_frame_time, now)
        previous_frame_time = now

        hand_result = tracker.process(frame)
        pointer_result = mapper.update(hand_result.index_tip)
        gesture_result = detector.update(
            hand_result.thumb_tip,
            hand_result.index_tip,
            int(now * 1000),
        )

        if mouse.is_control_enabled():
            _apply_mouse_control(mouse, pointer_result, gesture_result.should_click)

        debug_frame = debug_view.draw(
            frame,
            hand_result,
            mapper.last_frame_point,
            gesture_result,
            mouse.is_control_enabled(),
            fps,
        )

        cv2.imshow(WINDOW_NAME, debug_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("m"):
            mouse.set_control_enabled(not mouse.is_control_enabled())
        elif key == ord("q"):
            break


def _create_tracker() -> HandTracker:
    return HandTracker()


def _fps(previous_time: float, now: float) -> float:
    elapsed = now - previous_time
    if elapsed <= 0:
        return 0.0
    return 1.0 / elapsed


def _mirror_frame(cv2: Any, frame: Any) -> Any:
    return cv2.flip(frame, 1)


def _apply_mouse_control(
    mouse: MouseController,
    pointer_result: Any,
    should_click: bool,
) -> None:
    try:
        mouse.move(pointer_result)
        if should_click:
            mouse.left_click()
    except MouseFailsafeTriggered:
        mouse.set_control_enabled(False)


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required to run HandMouse. Install opencv-python."
        ) from exc

    return cv2


def _screen_size() -> tuple[int, int]:
    try:
        import pyautogui
    except ImportError as exc:
        raise RuntimeError(
            "PyAutoGUI is required to determine the screen size. Install pyautogui."
        ) from exc

    width, height = pyautogui.size()
    return int(width), int(height)


__all__ = ["main"]


if __name__ == "__main__":
    main()
