from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.pointer_mapper import FramePoint
from handmouse.interlock import InteractionInterlock, InterlockType


@dataclass(frozen=True)
class GestureConfig:
    pinch_close: float = 0.05
    pinch_open: float = 0.075
    confirm_frames: int = 2
    release_confirm_frames: int = 2
    cooldown_ms: int = 150
    emit_on_release: bool = True


class GestureState(Enum):
    PINCH_OPEN = auto()
    PINCH_PRESSED = auto()
    PINCH_HOLD = auto()
    COOLDOWN = auto()


@dataclass(frozen=True)
class GestureResult:
    state: GestureState
    should_click: bool
    pinch_distance: float | None


class GestureDetector:
    def __init__(self, config: GestureConfig, interlock: InteractionInterlock | None = None) -> None:
        self.config = config
        self.interlock = interlock
        self._state = GestureState.PINCH_OPEN
        self._close_count = 0
        self._release_count = 0
        self._cooldown_until_ms = 0

    def update(
        self,
        thumb: FramePoint | None,
        index: FramePoint | None,
        now_ms: int,
    ) -> GestureResult:
        if thumb is None or index is None:
            self.reset()
            return GestureResult(GestureState.PINCH_OPEN, False, None)

        distance = hypot(thumb.x - index.x, thumb.y - index.y)

        wants_active = distance < self.config.pinch_close or self._state != GestureState.PINCH_OPEN
        if wants_active:
            if self.interlock and not self.interlock.try_acquire(InterlockType.CLICK):
                self.reset()
                return GestureResult(GestureState.PINCH_OPEN, False, distance)
        else:
            if self.interlock:
                self.interlock.release(InterlockType.CLICK)

        if self._state == GestureState.COOLDOWN and now_ms < self._cooldown_until_ms:
            return GestureResult(GestureState.COOLDOWN, False, distance)

        if self._state == GestureState.COOLDOWN and now_ms >= self._cooldown_until_ms:
            self._state = GestureState.PINCH_OPEN
            self._close_count = 0
            self._release_count = 0
            self._cooldown_until_ms = 0

        if self._state == GestureState.PINCH_OPEN:
            return self._update_open(distance)

        return self._update_pressed_or_hold(distance, now_ms)

    def reset(self) -> None:
        self._state = GestureState.PINCH_OPEN
        self._close_count = 0
        self._release_count = 0
        self._cooldown_until_ms = 0
        if self.interlock:
            self.interlock.release(InterlockType.CLICK)

    def _update_open(self, distance: float) -> GestureResult:
        if distance < self.config.pinch_close:
            self._close_count += 1
            if self._close_count >= self.config.confirm_frames:
                self._state = GestureState.PINCH_PRESSED
                self._release_count = 0
                self._close_count = 0
                return GestureResult(self._state, False, distance)
            return GestureResult(GestureState.PINCH_OPEN, False, distance)

        self._close_count = 0
        return GestureResult(GestureState.PINCH_OPEN, False, distance)

    def _update_pressed_or_hold(self, distance: float, now_ms: int) -> GestureResult:
        if distance <= self.config.pinch_open:
            self._release_count = 0
            if self._state == GestureState.PINCH_PRESSED:
                self._state = GestureState.PINCH_HOLD
            return GestureResult(self._state, False, distance)

        self._release_count += 1
        if self._release_count >= self.config.release_confirm_frames:
            self._state = GestureState.COOLDOWN
            self._cooldown_until_ms = now_ms + self.config.cooldown_ms
            self._close_count = 0
            self._release_count = 0
            return GestureResult(GestureState.COOLDOWN, self.config.emit_on_release, distance)

        return GestureResult(self._state, False, distance)


__all__ = ["GestureConfig", "GestureDetector", "GestureResult", "GestureState"]
