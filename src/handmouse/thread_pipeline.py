from __future__ import annotations

import threading
import time
from typing import Any, Tuple

from handmouse.camera import Camera
from handmouse.hand_tracker import HandTracker, HandTrackingResult


class FrameBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame = None
        self._timestamp_ms = 0
        self._new_frame_event = threading.Event()

    def set(self, frame: Any, timestamp_ms: int) -> None:
        with self._lock:
            self._frame = frame
            self._timestamp_ms = timestamp_ms
        self._new_frame_event.set()

    def get(self) -> Tuple[Any, int]:
        with self._lock:
            return self._frame, self._timestamp_ms

    def wait_new_frame(self, timeout: float | None = None) -> bool:
        return self._new_frame_event.wait(timeout)

    def clear(self) -> None:
        self._new_frame_event.clear()


class ResultBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._result = None
        self._frame = None
        self._timestamp_ms = 0
        self._new_result_event = threading.Event()

    def set(self, result: HandTrackingResult, frame: Any, timestamp_ms: int) -> None:
        with self._lock:
            self._result = result
            self._frame = frame
            self._timestamp_ms = timestamp_ms
        self._new_result_event.set()

    def get(self) -> Tuple[HandTrackingResult | None, Any, int]:
        with self._lock:
            return self._result, self._frame, self._timestamp_ms

    def wait_new_result(self, timeout: float | None = None) -> bool:
        return self._new_result_event.wait(timeout)

    def clear(self) -> None:
        self._new_result_event.clear()


class CameraReader(threading.Thread):
    def __init__(self, camera: Camera) -> None:
        super().__init__(name="CameraReader", daemon=True)
        self.camera = camera
        self.buffer = FrameBuffer()
        self._stop_event = threading.Event()

    def run(self) -> None:
        fps_target = getattr(self.camera.config, "fps_target", 60)
        frame_interval = 1.0 / fps_target if fps_target > 0 else 0.016

        while not self._stop_event.is_set():
            start_time = time.perf_counter()
            try:
                ok, frame = self.camera.read()
                if ok and frame is not None:
                    now_ms = int(time.perf_counter() * 1000)
                    self.buffer.set(frame, now_ms)
            except Exception:
                pass

            elapsed = time.perf_counter() - start_time
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self) -> None:
        self._stop_event.set()


class InferenceWorker(threading.Thread):
    def __init__(self, reader: CameraReader, tracker: HandTracker) -> None:
        super().__init__(name="InferenceWorker", daemon=True)
        self.reader = reader
        self.tracker = tracker
        self.buffer = ResultBuffer()
        self._stop_event = threading.Event()

    def run(self) -> None:
        while not self._stop_event.is_set():
            if self.reader.buffer.wait_new_frame(timeout=0.1):
                self.reader.buffer.clear()
                frame, timestamp_ms = self.reader.buffer.get()
                if frame is not None:
                    try:
                        result = self.tracker.process(frame, frame_timestamp_ms=timestamp_ms)
                        self.buffer.set(result, frame, timestamp_ms)
                    except Exception:
                        pass

    def stop(self) -> None:
        self._stop_event.set()


__all__ = ["CameraReader", "InferenceWorker", "FrameBuffer", "ResultBuffer"]
