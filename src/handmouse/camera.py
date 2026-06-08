from __future__ import annotations

import time
from typing import Any

from handmouse.config import CameraConfig


BACKEND_CONSTANTS: dict[str, int] = {
    "CAP_DSHOW": 700,  # cv2.CAP_DSHOW
    "CAP_MSMF": 1400,  # cv2.CAP_MSMF
    "CAP_ANY": 0,  # cv2.CAP_ANY
}


class Camera:
    READ_RETRIES = 10
    READ_RETRY_DELAY_SECONDS = 0.03

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._capture: Any | None = None
        self._backend_name: str = "UNKNOWN"

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def open(self) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required to open the camera. Install opencv-python."
            ) from exc

        capture = self._open_with_preference(cv2)
        if capture is None:
            raise RuntimeError(
                f"Could not open camera at index {self.config.index} with any "
                f"preferred backend: {self.config.backend_preference}. Check Windows "
                f"camera permissions, close other apps using the camera, or change the "
                f"camera index in DEFAULT_CONFIG."
            )

        self._capture = capture

    def _open_with_preference(self, cv2: Any) -> Any | None:
        last_error: BaseException | None = None
        for backend_name in self.config.backend_preference:
            constant = BACKEND_CONSTANTS.get(backend_name)
            if constant is None:
                continue
            try:
                capture = cv2.VideoCapture(self.config.index, constant)
            except (AttributeError, TypeError, ValueError):
                capture = cv2.VideoCapture(self.config.index)

            if not capture.isOpened():
                capture.release()
                continue

            self._apply_runtime_settings(cv2, capture)
            self._backend_name = backend_name
            return capture

        try:
            capture = cv2.VideoCapture(self.config.index)
        except (AttributeError, TypeError, ValueError) as exc:
            last_error = exc
            capture = None

        if capture is not None and capture.isOpened():
            self._apply_runtime_settings(cv2, capture)
            self._backend_name = "CAP_ANY"
            return capture

        if capture is not None:
            capture.release()
        return None

    def _apply_runtime_settings(self, cv2: Any, capture: Any) -> None:
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)
        try:
            capture.set(cv2.CAP_PROP_FPS, float(self.config.fps_target))
        except (AttributeError, TypeError, ValueError):
            pass
        if self.config.buffer_size and self.config.buffer_size > 0:
            try:
                capture.set(cv2.CAP_PROP_BUFFERSIZE, int(self.config.buffer_size))
            except (AttributeError, TypeError, ValueError):
                pass

    def read(self) -> tuple[bool, Any]:
        if self._capture is None:
            raise RuntimeError("Camera is not open. Call open() before read().")

        for _ in range(self.READ_RETRIES):
            ok, frame = self._capture.read()
            if ok and frame is not None:
                return ok, frame
            time.sleep(self.READ_RETRY_DELAY_SECONDS)

        return False, None

    def release(self) -> None:
        if self._capture is not None:
            self._capture.release()
            self._capture = None


__all__ = ["BACKEND_CONSTANTS", "Camera"]
