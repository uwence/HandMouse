from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from handmouse.pointer_mapper import FramePoint


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
    ) -> None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise RuntimeError(
                "MediaPipe is required for hand tracking. Install mediapipe."
            ) from exc

        self._hands = mp.solutions.hands.Hands(
            static_image_mode=static_image_mode,
            max_num_hands=max_num_hands,
            min_detection_confidence=min_detection_confidence,
            min_tracking_confidence=min_tracking_confidence,
        )

    def process(self, frame_bgr: Any) -> HandTrackingResult:
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required to convert camera frames for MediaPipe."
            ) from exc

        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._hands.process(frame_rgb)

        if not result.multi_hand_landmarks:
            return HandTrackingResult(
                landmarks=[],
                thumb_tip=None,
                index_tip=None,
                raw_landmarks=None,
                handedness_label=None,
                handedness_confidence=None,
            )

        selected_index = 0
        selected_raw_landmarks = result.multi_hand_landmarks[selected_index]
        label, confidence = self._handedness(result, selected_index)
        landmarks = [
            FramePoint(landmark.x, landmark.y)
            for landmark in selected_raw_landmarks.landmark
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
        self._hands.close()

    @staticmethod
    def _landmark_at(landmarks: list[FramePoint], index: int) -> FramePoint | None:
        if index >= len(landmarks):
            return None
        return landmarks[index]

    @staticmethod
    def _handedness(result: Any, selected_index: int) -> tuple[str | None, float | None]:
        handedness = getattr(result, "multi_handedness", None)
        if not handedness or selected_index >= len(handedness):
            return None, None

        classifications = getattr(handedness[selected_index], "classification", None)
        if not classifications:
            return None, None

        classification = classifications[0]
        return (
            getattr(classification, "label", None),
            getattr(classification, "score", None),
        )


__all__ = ["HandTracker", "HandTrackingResult"]
