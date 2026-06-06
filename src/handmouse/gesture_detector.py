from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.config import GestureConfig
from handmouse.pointer_mapper import FramePoint


class GestureState(Enum):
    NO_HAND = auto()
    MOVING = auto()
    PINCH_CANDIDATE = auto()
    CLICK = auto()
    COOLDOWN = auto()


@dataclass(frozen=True)
class GestureResult:
    state: GestureState
    should_click: bool
    pinch_distance: float | None


class GestureDetector:
    def __init__(self, config: GestureConfig) -> None:
        self.config = config
        self._state = GestureState.NO_HAND
        self._pinch_started_ms: int | None = None
        self._cooldown_until_ms = 0
        self._released_after_click = True

    def update(
        self,
        thumb: FramePoint | None,
        index: FramePoint | None,
        now_ms: int,
    ) -> GestureResult:
        if thumb is None or index is None:
            self.reset()
            return GestureResult(GestureState.NO_HAND, False, None)

        distance = hypot(thumb.x - index.x, thumb.y - index.y)

        if self._state == GestureState.COOLDOWN:
            return self._update_cooldown(distance, now_ms)

        if distance < self.config.pinch_threshold:
            return self._update_pinch_candidate(distance, now_ms)

        self._state = GestureState.MOVING
        self._pinch_started_ms = None
        return GestureResult(self._state, False, distance)

    def reset(self) -> None:
        self._state = GestureState.NO_HAND
        self._pinch_started_ms = None
        self._cooldown_until_ms = 0
        self._released_after_click = True

    def _update_cooldown(self, distance: float, now_ms: int) -> GestureResult:
        if distance > self.config.release_threshold:
            self._released_after_click = True

        if now_ms < self._cooldown_until_ms or not self._released_after_click:
            return GestureResult(GestureState.COOLDOWN, False, distance)

        self._state = GestureState.MOVING
        self._pinch_started_ms = None
        return GestureResult(self._state, False, distance)

    def _update_pinch_candidate(self, distance: float, now_ms: int) -> GestureResult:
        if self._state != GestureState.PINCH_CANDIDATE:
            self._state = GestureState.PINCH_CANDIDATE
            self._pinch_started_ms = now_ms

        if self._pinch_started_ms is not None:
            held_ms = now_ms - self._pinch_started_ms
            if held_ms >= self.config.hold_ms:
                self._state = GestureState.COOLDOWN
                self._pinch_started_ms = None
                self._cooldown_until_ms = now_ms + self.config.cooldown_ms
                self._released_after_click = False
                return GestureResult(GestureState.CLICK, True, distance)

        return GestureResult(GestureState.PINCH_CANDIDATE, False, distance)


__all__ = ["GestureDetector", "GestureResult", "GestureState"]
