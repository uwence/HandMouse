from __future__ import annotations

from typing import Any

from handmouse.config import DEFAULT_CONFIG, AppConfig
from handmouse.gesture_detector import GestureResult, GestureState
from handmouse.hand_tracker import HandTrackingResult
from handmouse.pointer_mapper import FramePoint, ScreenPoint


HAND_CONNECTIONS: tuple[tuple[int, int], ...] = (
    (0, 1),
    (1, 2),
    (2, 3),
    (3, 4),
    (0, 5),
    (5, 6),
    (6, 7),
    (7, 8),
    (5, 9),
    (9, 10),
    (10, 11),
    (11, 12),
    (9, 13),
    (13, 14),
    (14, 15),
    (15, 16),
    (13, 17),
    (0, 17),
    (17, 18),
    (18, 19),
    (19, 20),
)


class DebugView:
    def __init__(self, config: AppConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def draw(
        self,
        frame: Any,
        hand_result: HandTrackingResult | None,
        pointer_result: ScreenPoint | FramePoint | Any | None,
        gesture_result: GestureResult | None,
        control_enabled: bool,
        fps: float,
    ) -> Any:
        cv2 = _load_cv2()
        width, height = _frame_dimensions(frame)

        self._draw_landmarks(cv2, frame, hand_result, width, height)
        self._draw_control_region(cv2, frame, width, height)
        self._draw_raw_index_tip(cv2, frame, hand_result, width, height)
        self._draw_pointer_target(cv2, frame, pointer_result, width, height)
        self._draw_status_panel(
            cv2,
            frame,
            hand_result,
            gesture_result,
            control_enabled,
            fps,
        )

        return frame

    def _draw_landmarks(
        self,
        cv2: Any,
        frame: Any,
        hand_result: HandTrackingResult | None,
        width: int,
        height: int,
    ) -> None:
        if hand_result is None:
            return

        raw_landmarks = getattr(hand_result, "raw_landmarks", None)
        if raw_landmarks is not None and self._draw_mediapipe_landmarks(frame, raw_landmarks):
            return

        landmarks = getattr(hand_result, "landmarks", None) or []
        if not landmarks:
            return

        pixels = [_normalized_point_to_pixel(point, width, height) for point in landmarks]
        for start, end in HAND_CONNECTIONS:
            if start < len(pixels) and end < len(pixels):
                cv2.line(frame, pixels[start], pixels[end], (80, 220, 120), 2)

        for pixel in pixels:
            cv2.circle(frame, pixel, 3, (40, 255, 160), -1)

    def _draw_mediapipe_landmarks(self, frame: Any, raw_landmarks: Any) -> bool:
        try:
            import mediapipe as mp
        except ImportError:
            return False

        try:
            mp.solutions.drawing_utils.draw_landmarks(
                frame,
                raw_landmarks,
                mp.solutions.hands.HAND_CONNECTIONS,
            )
        except Exception:
            return False

        return True

    def _draw_control_region(self, cv2: Any, frame: Any, width: int, height: int) -> None:
        region = self.config.pointer.control_region
        top_left = _normalized_xy_to_pixel(region.left, region.top, width, height)
        bottom_right = _normalized_xy_to_pixel(region.right, region.bottom, width, height)
        cv2.rectangle(frame, top_left, bottom_right, (255, 180, 40), 2)
        cv2.putText(
            frame,
            "CONTROL REGION",
            (top_left[0] + 8, max(20, top_left[1] + 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 180, 40),
            2,
            cv2.LINE_AA,
        )

    def _draw_raw_index_tip(
        self,
        cv2: Any,
        frame: Any,
        hand_result: HandTrackingResult | None,
        width: int,
        height: int,
    ) -> None:
        point = _index_tip(hand_result)
        if point is None:
            return

        pixel = _normalized_point_to_pixel(point, width, height)
        cv2.circle(frame, pixel, 8, (0, 190, 255), 2)
        cv2.circle(frame, pixel, 3, (0, 190, 255), -1)
        cv2.putText(
            frame,
            "raw index",
            (pixel[0] + 10, pixel[1] - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 190, 255),
            1,
            cv2.LINE_AA,
        )

    def _draw_pointer_target(
        self,
        cv2: Any,
        frame: Any,
        pointer_result: ScreenPoint | FramePoint | Any | None,
        width: int,
        height: int,
    ) -> None:
        point = _extract_pointer_point(pointer_result)
        if point is None:
            return

        if isinstance(point, ScreenPoint):
            _draw_screen_point_text(cv2, frame, point, height)
            return

        pixel = _point_to_pixel(point, width, height)
        if pixel is None:
            return

        cv2.drawMarker(
            frame,
            pixel,
            (255, 80, 255),
            markerType=cv2.MARKER_CROSS,
            markerSize=22,
            thickness=2,
            line_type=cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            "target",
            (pixel[0] + 10, pixel[1] + 18),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 80, 255),
            1,
            cv2.LINE_AA,
        )

    def _draw_status_panel(
        self,
        cv2: Any,
        frame: Any,
        hand_result: HandTrackingResult | None,
        gesture_result: GestureResult | None,
        control_enabled: bool,
        fps: float,
    ) -> None:
        lines = [
            f"Mode: {'CONTROL' if control_enabled else 'DEBUG'}",
            f"Gesture: {_gesture_state_name(gesture_result)}",
            f"Action: {_gesture_action_name(gesture_result)}",
            f"Active: {_active_state(gesture_result)}",
            f"Scroll: {_scroll_delta(gesture_result)}",
            f"FPS: {fps:.1f}",
            f"Pinch: {_pinch_distance(gesture_result)}",
            f"Hand: {_hand_info(hand_result)}",
        ]

        x = 14
        y = 28
        line_height = 24
        panel_width = max(250, max(len(line) for line in lines) * 12)
        panel_height = line_height * len(lines) + 16

        overlay = frame.copy()
        cv2.rectangle(overlay, (8, 8), (8 + panel_width, 8 + panel_height), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)

        mode_color = (80, 255, 120) if control_enabled else (80, 210, 255)
        for index, line in enumerate(lines):
            color = mode_color if index == 0 else (235, 235, 235)
            cv2.putText(
                frame,
                line,
                (x, y + index * line_height),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                color,
                2,
                cv2.LINE_AA,
            )


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required to draw the debug overlay. Install opencv-python."
        ) from exc

    return cv2


def _frame_dimensions(frame: Any) -> tuple[int, int]:
    shape = getattr(frame, "shape", None)
    if shape is None or len(shape) < 2:
        raise ValueError("frame must be an OpenCV-style image with height and width")

    height, width = int(shape[0]), int(shape[1])
    if width <= 0 or height <= 0:
        raise ValueError("frame must have positive height and width")

    return width, height


def _index_tip(hand_result: HandTrackingResult | None) -> FramePoint | None:
    if hand_result is None:
        return None

    index_tip = getattr(hand_result, "index_tip", None)
    if index_tip is not None:
        return index_tip

    landmarks = getattr(hand_result, "landmarks", None) or []
    if len(landmarks) > 8:
        return landmarks[8]

    return None


def _extract_pointer_point(pointer_result: ScreenPoint | FramePoint | Any | None) -> Any | None:
    if pointer_result is None:
        return None

    for attr in ("target_frame_point", "smoothed_frame_point", "frame_point", "target", "point"):
        value = getattr(pointer_result, attr, None)
        if value is not None:
            return value

    return pointer_result


def _point_to_pixel(point: Any, width: int, height: int) -> tuple[int, int] | None:
    if isinstance(point, FramePoint):
        return _normalized_point_to_pixel(point, width, height)

    x = getattr(point, "x", None)
    y = getattr(point, "y", None)
    if x is None or y is None:
        return None

    try:
        x_float = float(x)
        y_float = float(y)
    except (TypeError, ValueError):
        return None

    if 0.0 <= x_float <= 1.0 and 0.0 <= y_float <= 1.0:
        return _normalized_xy_to_pixel(x_float, y_float, width, height)

    return (
        _clamp_int(round(x_float), 0, width - 1),
        _clamp_int(round(y_float), 0, height - 1),
    )


def _draw_screen_point_text(cv2: Any, frame: Any, point: ScreenPoint, height: int) -> None:
    text = f"target screen: {point.x}, {point.y}"
    origin = (14, max(24, height - 16))
    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 0, 0),
        3,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        text,
        origin,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (255, 80, 255),
        1,
        cv2.LINE_AA,
    )


def _normalized_point_to_pixel(point: FramePoint, width: int, height: int) -> tuple[int, int]:
    return _normalized_xy_to_pixel(point.x, point.y, width, height)


def _normalized_xy_to_pixel(x: float, y: float, width: int, height: int) -> tuple[int, int]:
    return (
        _clamp_int(round(float(x) * (width - 1)), 0, width - 1),
        _clamp_int(round(float(y) * (height - 1)), 0, height - 1),
    )


def _clamp_int(value: int, lower: int, upper: int) -> int:
    return max(lower, min(upper, value))


def _gesture_state_name(gesture_result: GestureResult | None) -> str:
    if gesture_result is None:
        return "n/a"

    state = getattr(gesture_result, "state", None)
    if isinstance(state, GestureState):
        return state.name

    return getattr(state, "name", str(state))


def _gesture_action_name(gesture_result: Any | None) -> str:
    action = getattr(gesture_result, "action", None)
    if action is None:
        return "n/a"

    return getattr(action, "name", str(action))


def _active_state(gesture_result: Any | None) -> str:
    active = getattr(gesture_result, "active", None)
    if active is None:
        return "n/a"
    return "yes" if active else "no"


def _scroll_delta(gesture_result: Any | None) -> str:
    delta = getattr(gesture_result, "scroll_delta", None)
    if delta is None:
        return "n/a"
    return str(delta)


def _pinch_distance(gesture_result: GestureResult | None) -> str:
    distance = getattr(gesture_result, "pinch_distance", None)
    if distance is None:
        return "n/a"

    try:
        return f"{float(distance):.3f}"
    except (TypeError, ValueError):
        return str(distance)


def _hand_info(hand_result: HandTrackingResult | None) -> str:
    if hand_result is None:
        return "n/a"

    label = getattr(hand_result, "handedness_label", None)
    confidence = getattr(hand_result, "handedness_confidence", None)
    if label is None and confidence is None:
        return "selected"
    if confidence is None:
        return str(label)
    if label is None:
        return f"selected ({float(confidence):.2f})"

    return f"{label} ({float(confidence):.2f})"


__all__ = ["DebugView"]
