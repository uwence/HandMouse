from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import numpy as np

from handmouse.app import _run_loop
from handmouse.camera import Camera
from handmouse.config import CameraConfig, DEFAULT_CONFIG
from handmouse.engagement import EngagementConfig, EngagementFSM
from handmouse.gesture_detector import GestureConfig, GestureDetector
from handmouse.grab_scroll_detector import GrabScrollConfig, GrabScrollDetector
from handmouse.hand_tracker import HandTracker, HandTrackingResult
from handmouse.interlock import InteractionInterlock
from handmouse.mouse_controller import MouseController
from handmouse.move_mode import MoveModeConfig, MoveModeController
from handmouse.pointer_engine import PointerEngine, PointerEngineConfig
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutDetector
from handmouse.thread_pipeline import CameraReader, InferenceWorker


class MockCamera(Camera):
    def __init__(self, config: CameraConfig) -> None:
        super().__init__(config)
        self._backend_name = "MOCK"
        self._frame = np.zeros((config.height, config.width, 3), dtype=np.uint8)

    def open(self) -> None:
        pass

    def read(self) -> tuple[bool, Any]:
        # Return a synthetic frame immediately
        return True, self._frame

    def release(self) -> None:
        pass


class MockTracker(HandTracker):
    def __init__(self) -> None:
        pass

    def process(self, frame: Any, frame_timestamp_ms: int | None = None) -> HandTrackingResult:
        # Simulate 10ms inference overhead
        time.sleep(0.010)
        return HandTrackingResult(
            landmarks=[],
            thumb_tip=None,
            index_tip=None,
            raw_landmarks=None,
            handedness_label=None,
            handedness_confidence=None,
        )

    def close(self) -> None:
        pass


class MockCv2:
    def __init__(self) -> None:
        self.frame_count = 0

    def flip(self, frame: Any, flip_code: int) -> Any:
        return frame

    def waitKey(self, delay: int) -> int:
        self.frame_count += 1
        # Fast-path wait: sleep for 1ms instead of blocking 16ms to let the benchmark run fast
        time.sleep(0.001)
        if self.frame_count >= 100:
            return ord("q")  # Exit loop after 100 frames
        return 0

    def imshow(self, name: str, frame: Any) -> None:
        pass


class MockDebugView:
    def __init__(self, config: Any) -> None:
        pass

    def draw(self, frame: Any, hand_result: Any, gesture_result: Any, is_active: bool, telemetry: Any) -> Any:
        return frame


def run_benchmark() -> float:
    config = DEFAULT_CONFIG
    camera = MockCamera(config.camera)
    tracker = MockTracker()
    mouse = MouseController()
    shortcut = ShortcutController()
    cv2 = MockCv2()

    pointer = PointerEngine(
        PointerEngineConfig(
            screen_width=1920,
            screen_height=1080,
            control_region=config.pointer.control_region,
        )
    )
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(), interlock=interlock)
    grab_scroll = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)
    shortcut_detector = ShortcutDetector(config.shortcut)
    engagement = EngagementFSM(EngagementConfig())
    move_mode = MoveModeController(MoveModeConfig())
    debug_view = MockDebugView(config)

    camera_reader = CameraReader(camera)
    inference_worker = InferenceWorker(camera_reader, tracker)

    camera_reader.start()
    inference_worker.start()

    start_time = time.perf_counter()
    try:
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
            camera_reader=camera_reader,
            inference_worker=inference_worker,
        )
    finally:
        inference_worker.stop()
        camera_reader.stop()
        inference_worker.join(timeout=1.0)
        camera_reader.join(timeout=1.0)

    elapsed = time.perf_counter() - start_time
    fps = cv2.frame_count / elapsed if elapsed > 0 else 0
    print(f"Benchmark finished: processed {cv2.frame_count} frames in {elapsed:.3f} seconds.")
    print(f"Main thread rendering FPS: {fps:.2f}")
    return fps


if __name__ == "__main__":
    fps = run_benchmark()
    assert fps >= 55.0, f"FPS is too low: {fps:.2f} < 55.0"
    print("Benchmark PASSED!")
