from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot
from statistics import median
from typing import Any

from handmouse.config import ControlRegion
from handmouse.pointer_mapper import FramePoint, ScreenDelta


@dataclass(frozen=True)
class PointerEngineConfig:
    screen_width: int
    screen_height: int
    control_region: ControlRegion
    v_jitter: float = 0.20
    v_mid: float = 1.0
    v_fast: float = 3.0
    g_lo: float = 0.85
    g_hi: float = 3.0
    depth_gamma: float = 0.9
    z_min: float = 0.70
    z_max: float = 1.25
    z_scale_reference: float | None = None
    dead_zone_radius: float = 0.0
    missing_frames_to_idle: int = 4
    pixel_per_palm_width: float | None = None


class PointerEngineState(Enum):
    IDLE = auto()
    ACTIVE = auto()
    COOLDOWN = auto()


class PointerEngine:
    _Wrist = 0
    _IndexMcp = 5
    _MiddleMcp = 9
    _PinkyMcp = 17
    _IndexTip = 8

    def __init__(self, config: PointerEngineConfig) -> None:
        if config.screen_width <= 0 or config.screen_height <= 0:
            raise ValueError("screen dimensions must be positive")

        region = config.control_region
        if region.right <= region.left or region.bottom <= region.top:
            raise ValueError("control region must have positive width and height")

        if config.missing_frames_to_idle < 1:
            raise ValueError("missing_frames_to_idle must be at least 1")

        if config.pixel_per_palm_width is not None and config.pixel_per_palm_width <= 0:
            raise ValueError("pixel_per_palm_width must be positive")

        if config.dead_zone_radius < 0:
            raise ValueError("dead_zone_radius must be non-negative")

        self.config = config
        self._state = PointerEngineState.IDLE
        self._previous_point: FramePoint | None = None
        self._previous_timestamp_ms: int | None = None
        self._missing_frames = 0
        self._last_velocity: float | None = None
        self._last_gain: float | None = None
        self._last_depth_factor: float | None = None
        self._last_hand_scale: float | None = None
        self._scale_reference = config.z_scale_reference

    def update(self, hand_result: Any, now_ms: int) -> ScreenDelta | None:
        landmarks = self._extract_landmarks(hand_result)
        index_tip = self._extract_index_tip(hand_result, landmarks)
        hand_scale = self._estimate_hand_scale(landmarks) if landmarks is not None else None

        if index_tip is None or hand_scale is None or not self._scale_in_range(hand_scale):
            return self._handle_missing_hand()

        normalized_point = self._normalize_index_tip(index_tip)
        if self._previous_point is None or self._previous_timestamp_ms is None:
            self._anchor(normalized_point, now_ms, hand_scale)
            return None

        dt_seconds = max((now_ms - self._previous_timestamp_ms) / 1000.0, 1e-6)
        u_x = normalized_point.x - self._previous_point.x
        u_y = normalized_point.y - self._previous_point.y
        displacement = hypot(u_x, u_y)
        velocity = displacement / dt_seconds

        depth_factor = self._depth_factor(hand_scale)
        gain = self._gain_for_velocity(velocity, displacement)
        pixel_per_palm_width = (
            self.config.pixel_per_palm_width if self.config.pixel_per_palm_width is not None else self.config.screen_height
        )

        if gain == 0.0:
            delta = ScreenDelta(0, 0)
        else:
            delta = ScreenDelta(
                round(pixel_per_palm_width * gain * depth_factor * u_x),
                round(pixel_per_palm_width * gain * depth_factor * u_y),
            )

        self._previous_point = normalized_point
        self._previous_timestamp_ms = now_ms
        self._missing_frames = 0
        self._state = PointerEngineState.ACTIVE
        self._last_velocity = velocity
        self._last_gain = gain
        self._last_depth_factor = depth_factor
        self._last_hand_scale = hand_scale

        return delta

    def reset(self) -> None:
        self._state = PointerEngineState.IDLE
        self._previous_point = None
        self._previous_timestamp_ms = None
        self._missing_frames = 0
        self._last_velocity = None
        self._last_gain = None
        self._last_depth_factor = None
        self._last_hand_scale = None
        if self.config.z_scale_reference is None:
            self._scale_reference = None

    @property
    def last_velocity(self) -> float | None:
        return self._last_velocity

    @property
    def last_gain(self) -> float | None:
        return self._last_gain

    @property
    def last_depth_factor(self) -> float | None:
        return self._last_depth_factor

    @property
    def last_hand_scale(self) -> float | None:
        return self._last_hand_scale

    @property
    def state(self) -> PointerEngineState:
        return self._state

    def _handle_missing_hand(self) -> ScreenDelta | None:
        self._previous_point = None
        self._previous_timestamp_ms = None
        self._last_velocity = None
        self._last_gain = None
        self._last_depth_factor = None
        self._last_hand_scale = None
        self._missing_frames += 1
        if self._missing_frames >= self.config.missing_frames_to_idle:
            self._state = PointerEngineState.IDLE
        else:
            self._state = PointerEngineState.COOLDOWN
        return None

    def _anchor(self, point: FramePoint, now_ms: int, hand_scale: float) -> None:
        self._previous_point = point
        self._previous_timestamp_ms = now_ms
        self._missing_frames = 0
        self._state = PointerEngineState.ACTIVE
        self._last_velocity = None
        self._last_gain = None
        self._last_depth_factor = 1.0
        self._last_hand_scale = hand_scale
        if self._scale_reference is None:
            self._scale_reference = hand_scale

    def _normalize_index_tip(self, point: FramePoint) -> FramePoint:
        region = self.config.control_region
        normalized_x = self._clamp((point.x - region.left) / (region.right - region.left), 0.0, 1.0)
        normalized_y = self._clamp((point.y - region.top) / (region.bottom - region.top), 0.0, 1.0)
        return FramePoint(normalized_x, normalized_y)

    def _depth_factor(self, hand_scale: float) -> float:
        if self._scale_reference is None:
            self._scale_reference = hand_scale

        raw = (self._scale_reference / hand_scale) ** self.config.depth_gamma
        return self._clamp(raw, self.config.z_min, self.config.z_max)

    def _gain_for_velocity(self, velocity: float, displacement: float) -> float:
        if (
            self.config.dead_zone_radius > 0
            and displacement < self.config.dead_zone_radius
        ) or velocity < self.config.v_jitter:
            return 0.0

        if velocity < self.config.v_mid:
            span = self.config.v_mid - self.config.v_jitter
            if span <= 0:
                return 1.0
            ratio = (velocity - self.config.v_jitter) / span
            return self.config.g_lo + (1.0 - self.config.g_lo) * self._clamp(ratio, 0.0, 1.0)

        t_span = self.config.v_fast - self.config.v_mid
        if t_span <= 0:
            return self.config.g_hi

        t = self._clamp((velocity - self.config.v_mid) / t_span, 0.0, 1.0)
        smooth = t * t * (3.0 - 2.0 * t)
        return 1.0 + (self.config.g_hi - 1.0) * smooth

    def _extract_landmarks(self, hand_result: Any) -> list[FramePoint] | None:
        if hand_result is None:
            return None

        landmarks = getattr(hand_result, "landmarks", None)
        if not landmarks:
            return None

        return landmarks

    def _extract_index_tip(
        self,
        hand_result: Any,
        landmarks: list[FramePoint] | None,
    ) -> FramePoint | None:
        if hand_result is not None:
            index_tip = getattr(hand_result, "index_tip", None)
            if index_tip is not None:
                return index_tip

        if landmarks is None or len(landmarks) <= self._IndexTip:
            return None

        return landmarks[self._IndexTip]

    def _estimate_hand_scale(self, landmarks: list[FramePoint]) -> float | None:
        required_indices = (self._Wrist, self._IndexMcp, self._MiddleMcp, self._PinkyMcp)
        if len(landmarks) <= max(required_indices):
            return None

        wrist = landmarks[self._Wrist]
        index_mcp = landmarks[self._IndexMcp]
        middle_mcp = landmarks[self._MiddleMcp]
        pinky_mcp = landmarks[self._PinkyMcp]

        return median(
            (
                hypot(index_mcp.x - pinky_mcp.x, index_mcp.y - pinky_mcp.y),
                hypot(wrist.x - middle_mcp.x, wrist.y - middle_mcp.y),
                hypot(wrist.x - index_mcp.x, wrist.y - index_mcp.y),
            )
        )

    def _scale_in_range(self, hand_scale: float) -> bool:
        return 0.05 <= hand_scale <= 0.5

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))


__all__ = [
    "PointerEngine",
    "PointerEngineConfig",
    "PointerEngineState",
]
