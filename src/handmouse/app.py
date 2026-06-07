from __future__ import annotations

import time
from typing import Any

from handmouse.camera import Camera
from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugView
from handmouse.hand_tracker import HandTracker
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutDetector


WINDOW_NAME = "HandMouse"


def main() -> None:
    config = DEFAULT_CONFIG
    cv2 = _load_cv2()
    shortcuts = ShortcutController()

    camera = Camera(config.camera)
    tracker: HandTracker | None = None

    try:
        camera.open()
        tracker = _create_tracker()
        detector = ShortcutDetector(config.shortcut)
        debug_view = DebugView(config)

        _run_loop(
            cv2=cv2,
            camera=camera,
            tracker=tracker,
            detector=detector,
            shortcuts=shortcuts,
            debug_view=debug_view,
        )
    finally:
        shortcuts.set_enabled(False)
        camera.release()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()


def _run_loop(
    *,
    cv2: Any,
    camera: Camera,
    tracker: HandTracker,
    detector: ShortcutDetector,
    shortcuts: ShortcutController,
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
        shortcut_result = detector.update(hand_result.index_tip, int(now * 1000))

        if shortcuts.is_enabled():
            shortcuts.execute(shortcut_result.action)

        debug_frame = debug_view.draw(
            frame,
            hand_result,
            hand_result.index_tip,
            shortcut_result,
            shortcuts.is_enabled(),
            fps,
        )

        cv2.imshow(WINDOW_NAME, debug_frame)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("m"):
            shortcuts.set_enabled(not shortcuts.is_enabled())
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
