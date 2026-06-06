from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from handmouse.config import PointerConfig


@dataclass(frozen=True)
class FramePoint:
    x: float
    y: float


@dataclass(frozen=True)
class ScreenPoint:
    x: int
    y: int


class PointerMapper:
    def __init__(self, screen_width: int, screen_height: int, config: PointerConfig) -> None:
        if screen_width <= 0 or screen_height <= 0:
            raise ValueError("screen dimensions must be positive")

        region = config.control_region
        if region.right <= region.left or region.bottom <= region.top:
            raise ValueError("control region must have positive width and height")

        self.screen_width = screen_width
        self.screen_height = screen_height
        self.config = config
        self._previous_x: float | None = None
        self._previous_y: float | None = None
        self._previous_output: ScreenPoint | None = None

    def update(self, point: FramePoint | None) -> ScreenPoint | None:
        if point is None:
            self.reset()
            return None

        target_x, target_y = self._map_to_screen(point)

        if self._previous_x is None or self._previous_y is None:
            smoothed_x = target_x
            smoothed_y = target_y
        else:
            smoothing = self._clamp(self.config.smoothing, 0.0, 1.0)
            smoothed_x = self._previous_x + smoothing * (target_x - self._previous_x)
            smoothed_y = self._previous_y + smoothing * (target_y - self._previous_y)

        self._previous_x = smoothed_x
        self._previous_y = smoothed_y

        output = ScreenPoint(round(smoothed_x), round(smoothed_y))
        if self._is_inside_dead_zone(output):
            return self._previous_output

        self._previous_output = output
        return output

    def reset(self) -> None:
        self._previous_x = None
        self._previous_y = None
        self._previous_output = None

    def _map_to_screen(self, point: FramePoint) -> tuple[float, float]:
        region = self.config.control_region
        clamped_x = min(max(point.x, region.left), region.right)
        clamped_y = min(max(point.y, region.top), region.bottom)

        normalized_x = (clamped_x - region.left) / (region.right - region.left)
        normalized_y = (clamped_y - region.top) / (region.bottom - region.top)

        return (
            normalized_x * (self.screen_width - 1),
            normalized_y * (self.screen_height - 1),
        )

    def _is_inside_dead_zone(self, output: ScreenPoint) -> bool:
        if self._previous_output is None or self.config.dead_zone_px <= 0:
            return False

        distance = hypot(
            output.x - self._previous_output.x,
            output.y - self._previous_output.y,
        )
        return distance < self.config.dead_zone_px

    @staticmethod
    def _clamp(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))


__all__ = ["FramePoint", "PointerMapper", "ScreenPoint"]
