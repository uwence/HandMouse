from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from handmouse.config import DEFAULT_CONFIG, AppConfig
from handmouse.engagement import EngagementResult
from handmouse.gesture_detector import GestureResult, GestureState
from handmouse.hand_tracker import HandTrackingResult
from handmouse.pointer_engine import PointerEngine
from handmouse.pointer_mapper import FramePoint


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


@dataclass(frozen=True)
class DebugTelemetry:
    """Optional runtime stats to overlay on the debug view."""

    fps: float
    frame_age_ms: int | None
    backend_name: str | None
    pointer: PointerEngine | None = None
    engagement: EngagementResult | None = None
    grab_scroll: Any | None = None


class DebugView:
    PINCH_BAR_MAX_DISTANCE = 0.15
    PINCH_CLOSE_THRESHOLD = 0.05
    PINCH_OPEN_THRESHOLD = 0.075

    def __init__(self, config: AppConfig = DEFAULT_CONFIG) -> None:
        self.config = config

    def draw(
        self,
        frame: Any,
        hand_result: HandTrackingResult | None,
        gesture_result: GestureResult | None,
        control_enabled: bool,
        telemetry: DebugTelemetry | None = None,
    ) -> Any:
        cv2 = _load_cv2()
        width, height = _frame_dimensions(frame)

        self._draw_landmarks(cv2, frame, hand_result, width, height)
        self._draw_control_region(cv2, frame, width, height)
        self._draw_raw_index_tip(cv2, frame, hand_result, width, height)
        self._draw_pointer_target(cv2, frame, telemetry, width, height)
        self._draw_status_panel(
            cv2,
            frame,
            hand_result,
            gesture_result,
            control_enabled,
            telemetry,
        )
        self._draw_pinch_bar(cv2, frame, gesture_result, height)

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
        telemetry: DebugTelemetry | None,
        width: int,
        height: int,
    ) -> None:
        if telemetry is None or telemetry.pointer is None:
            return
        last_point = telemetry.pointer.last_frame_point
        if last_point is None:
            return
        pixel = _normalized_point_to_pixel(last_point, width, height)
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
            "pointer",
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
        telemetry: DebugTelemetry | None,
    ) -> None:
        engagement_state = (
            telemetry.engagement.state.name
            if telemetry is not None and telemetry.engagement is not None
            else "n/a"
        )
        engagement_active = (
            "yes"
            if telemetry is not None
            and telemetry.engagement is not None
            and telemetry.engagement.is_active
            else "no"
        )
        engagement_reason = (
            telemetry.engagement.reason
            if telemetry is not None and telemetry.engagement is not None
            else "n/a"
        )

        pointer_velocity = (
            f"{telemetry.pointer.last_velocity:.2f}"
            if telemetry is not None
            and telemetry.pointer is not None
            and telemetry.pointer.last_velocity is not None
            else "n/a"
        )
        pointer_gain = (
            f"{telemetry.pointer.last_gain:.2f}"
            if telemetry is not None
            and telemetry.pointer is not None
            and telemetry.pointer.last_gain is not None
            else "n/a"
        )
        pointer_depth = (
            f"{telemetry.pointer.last_depth_factor:.2f}"
            if telemetry is not None
            and telemetry.pointer is not None
            and telemetry.pointer.last_depth_factor is not None
            else "n/a"
        )
        pointer_hand_scale = (
            f"{telemetry.pointer.last_hand_scale:.3f}"
            if telemetry is not None
            and telemetry.pointer is not None
            and telemetry.pointer.last_hand_scale is not None
            else "n/a"
        )
        pointer_state = (
            telemetry.pointer.state.name
            if telemetry is not None and telemetry.pointer is not None
            else "n/a"
        )

        pinch_distance = (
            f"{gesture_result.pinch_distance:.3f}"
            if gesture_result is not None and gesture_result.pinch_distance is not None
            else "n/a"
        )

        grab_state = (
            telemetry.grab_scroll.state.name
            if telemetry is not None and telemetry.grab_scroll is not None
            else "n/a"
        )
        grab_active = (
            "yes"
            if telemetry is not None
            and telemetry.grab_scroll is not None
            and telemetry.grab_scroll.active
            else "no"
        )
        grab_scroll = (
            str(telemetry.grab_scroll.scroll_delta)
            if telemetry is not None and telemetry.grab_scroll is not None
            else "n/a"
        )

        fps_value = telemetry.fps if telemetry is not None else 0.0
        frame_age = (
            f"{telemetry.frame_age_ms} ms"
            if telemetry is not None and telemetry.frame_age_ms is not None
            else "n/a"
        )
        backend = (
            telemetry.backend_name
            if telemetry is not None and telemetry.backend_name is not None
            else "n/a"
        )

        lines = [
            f"Mode: {'CONTROL' if control_enabled else 'DEBUG'}",
            f"Engagement: {engagement_state} (active={engagement_active}, reason={engagement_reason})",
            f"Pointer: state={pointer_state} v={pointer_velocity} gain={pointer_gain} depth={pointer_depth} scale={pointer_hand_scale}",
            f"Pinch: state={_gesture_state_name(gesture_result)} d={pinch_distance} (close=0.050 open=0.075)",
            f"Grab: state={grab_state} active={grab_active} scroll={grab_scroll}",
            f"FPS: {fps_value:.1f}",
            f"Frame age: {frame_age}",
            f"Backend: {backend}",
            f"Hand: {_hand_info(hand_result)}",
        ]

        x = 14
        y = 28
        line_height = 22
        panel_width = max(380, max(len(line) for line in lines) * 11)
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
                0.55,
                color,
                2,
                cv2.LINE_AA,
            )

    def _draw_pinch_bar(
        self,
        cv2: Any,
        frame: Any,
        gesture_result: GestureResult | None,
        height: int,
    ) -> None:
        if gesture_result is None or gesture_result.pinch_distance is None:
            return

        distance = gesture_result.pinch_distance
        bar_x = 14
        bar_y = max(60, height - 40)
        bar_w = 280
        bar_h = 14

        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h), (40, 40, 40), -1)

        normalized = min(max(distance / self.PINCH_BAR_MAX_DISTANCE, 0.0), 1.0)
        fill_w = int(bar_w * normalized)

        close_x = bar_x + int(bar_w * (self.PINCH_CLOSE_THRESHOLD / self.PINCH_BAR_MAX_DISTANCE))
        cv2.line(frame, (close_x, bar_y - 4), (close_x, bar_y + bar_h + 4), (80, 255, 120), 2)

        open_x = bar_x + int(bar_w * (self.PINCH_OPEN_THRESHOLD / self.PINCH_BAR_MAX_DISTANCE))
        cv2.line(frame, (open_x, bar_y - 4), (open_x, bar_y + bar_h + 4), (80, 180, 255), 2)

        if distance < self.PINCH_CLOSE_THRESHOLD:
            fill_color = (80, 255, 120)
        elif distance < self.PINCH_OPEN_THRESHOLD:
            fill_color = (80, 200, 255)
        else:
            fill_color = (180, 180, 180)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h), fill_color, -1)

        cv2.putText(
            frame,
            "pinch d",
            (bar_x, bar_y - 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (220, 220, 220),
            1,
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


__all__ = ["DebugTelemetry", "DebugView"]
