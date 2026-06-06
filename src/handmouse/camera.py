from __future__ import annotations

import time
from typing import Any

from handmouse.config import CameraConfig


class Camera:
    READ_RETRIES = 10
    READ_RETRY_DELAY_SECONDS = 0.03

    def __init__(self, config: CameraConfig) -> None:
        self.config = config
        self._capture: Any | None = None

    def open(self) -> None:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required to open the camera. Install opencv-python."
            ) from exc

        capture = cv2.VideoCapture(self.config.index)
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.height)

        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Could not open camera at index {self.config.index}.")

        self._capture = capture

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


__all__ = ["Camera"]
