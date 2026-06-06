from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from handmouse.pointer_mapper import FramePoint


HAND_LANDMARKER_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
MODEL_ENV_VAR = "HANDMOUSE_MODEL_PATH"


@dataclass(frozen=True)
class HandTrackingResult:
    landmarks: list[FramePoint]
    thumb_tip: FramePoint | None
    index_tip: FramePoint | None
    raw_landmarks: Any | None
    handedness_label: str | None
    handedness_confidence: float | None


class HandTracker:
    THUMB_TIP = 4
    INDEX_TIP = 8

    def __init__(
        self,
        *,
        static_image_mode: bool = False,
        max_num_hands: int = 2,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model_path: str | Path | None = None,
    ) -> None:
        try:
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            from mediapipe.tasks.python.core.base_options import BaseOptions
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is required for hand tracking. Install mediapipe."
            ) from exc

        resolved_model_path = _resolve_model_path(model_path)
        options = vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(resolved_model_path)),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=max_num_hands,
            min_hand_detection_confidence=min_detection_confidence,
            min_hand_presence_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )
        self._mp = mp
        self._landmarker = vision.HandLandmarker.create_from_options(options)
        self._hands = self._landmarker
        self._static_image_mode = static_image_mode

    def process(self, frame_bgr: Any) -> HandTrackingResult:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required to convert camera frames for MediaPipe."
            ) from exc

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(
            image_format=self._mp.ImageFormat.SRGB,
            data=frame_rgb,
        )
        result = self._landmarker.detect(image)

        if not result.hand_landmarks:
            return HandTrackingResult(
                landmarks=[],
                thumb_tip=None,
                index_tip=None,
                raw_landmarks=None,
                handedness_label=None,
                handedness_confidence=None,
            )

        selected_index = 0
        selected_raw_landmarks = result.hand_landmarks[selected_index]
        label, confidence = self._handedness(result, selected_index)
        landmarks = [
            FramePoint(landmark.x, landmark.y)
            for landmark in selected_raw_landmarks
        ]

        return HandTrackingResult(
            landmarks=landmarks,
            thumb_tip=self._landmark_at(landmarks, self.THUMB_TIP),
            index_tip=self._landmark_at(landmarks, self.INDEX_TIP),
            raw_landmarks=selected_raw_landmarks,
            handedness_label=label,
            handedness_confidence=confidence,
        )

    def close(self) -> None:
        landmarker = getattr(self, "_landmarker", None)
        if landmarker is None:
            return

        try:
            landmarker.close()
        finally:
            self._landmarker = None
            self._hands = None

    @staticmethod
    def _landmark_at(landmarks: list[FramePoint], index: int) -> FramePoint | None:
        if index >= len(landmarks):
            return None
        return landmarks[index]

    @staticmethod
    def _handedness(result: Any, selected_index: int) -> tuple[str | None, float | None]:
        handedness = getattr(result, "handedness", None)
        if not handedness or selected_index >= len(handedness):
            return None, None

        classifications = handedness[selected_index]
        if not classifications:
            return None, None

        classification = classifications[0]
        return (
            getattr(classification, "category_name", None)
            or getattr(classification, "display_name", None),
            getattr(classification, "score", None),
        )


def _resolve_model_path(model_path: str | Path | None) -> Path:
    configured_path = model_path or os.environ.get(MODEL_ENV_VAR)
    path = Path(configured_path) if configured_path else _default_model_path()
    if path.exists():
        return path

    _download_model(path)
    return path


def _default_model_path() -> Path:
    return Path.home() / ".handmouse" / "models" / "hand_landmarker.task"


def _download_model(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urlopen(HAND_LANDMARKER_MODEL_URL, timeout=30) as response:
            path.write_bytes(response.read())
    except (OSError, URLError) as exc:
        raise RuntimeError(
            "Hand landmarker model is required for MediaPipe Tasks. "
            f"Download {HAND_LANDMARKER_MODEL_URL} to {path}, or set "
            f"{MODEL_ENV_VAR} to an existing hand_landmarker.task file."
        ) from exc


__all__ = ["HandTracker", "HandTrackingResult"]
