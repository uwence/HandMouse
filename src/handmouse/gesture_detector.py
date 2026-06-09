from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.types import FramePoint
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
    right_state: GestureState = GestureState.PINCH_OPEN
    should_right_click: bool = False
    right_pinch_distance: float | None = None
    should_double_click: bool = False


class GestureDetector:
    def __init__(self, config: GestureConfig, interlock: InteractionInterlock | None = None) -> None:
        self.config = config
        self.interlock = interlock

        # Left pinch states (thumb + index)
        self._left_state = GestureState.PINCH_OPEN
        self._left_close_count = 0
        self._left_release_count = 0
        self._left_cooldown_until_ms = 0
        self._last_left_click_ms = 0

        # Right pinch states (thumb + middle)
        self._right_state = GestureState.PINCH_OPEN
        self._right_close_count = 0
        self._right_release_count = 0
        self._right_cooldown_until_ms = 0

    @property
    def _state(self) -> GestureState:
        return self._left_state

    @_state.setter
    def _state(self, value: GestureState) -> None:
        self._left_state = value

    @property
    def _close_count(self) -> int:
        return self._left_close_count

    @_close_count.setter
    def _close_count(self, value: int) -> None:
        self._left_close_count = value

    @property
    def _release_count(self) -> int:
        return self._left_release_count

    @_release_count.setter
    def _release_count(self, value: int) -> None:
        self._left_release_count = value

    @property
    def _cooldown_until_ms(self) -> int:
        return self._left_cooldown_until_ms

    @_cooldown_until_ms.setter
    def _cooldown_until_ms(self, value: int) -> None:
        self._left_cooldown_until_ms = value

    def update(
        self,
        thumb: FramePoint | None,
        index: FramePoint | None,
        now_ms: int,
        middle: FramePoint | None = None,
    ) -> GestureResult:
        if thumb is None:
            self.reset()
            return GestureResult(
                GestureState.PINCH_OPEN, False, None,
                GestureState.PINCH_OPEN, False, None, False
            )

        left_dist = hypot(thumb.x - index.x, thumb.y - index.y) if index is not None else None
        right_dist = hypot(thumb.x - middle.x, thumb.y - middle.y) if middle is not None else None

        # Interlock check
        left_wants_active = left_dist is not None and (left_dist < self.config.pinch_close or self._left_state != GestureState.PINCH_OPEN)
        right_wants_active = right_dist is not None and (right_dist < self.config.pinch_close or self._right_state != GestureState.PINCH_OPEN)

        wants_active = left_wants_active or right_wants_active
        if wants_active:
            if self.interlock and not self.interlock.try_acquire(InterlockType.CLICK):
                self.reset()
                return GestureResult(
                    GestureState.PINCH_OPEN, False, left_dist,
                    GestureState.PINCH_OPEN, False, right_dist, False
                )
        else:
            if self.interlock:
                self.interlock.release(InterlockType.CLICK)

        # 1. Update Left State Machine
        should_click = False
        should_double_click = False

        if self._right_state != GestureState.PINCH_OPEN:
            # Right click active, reset left click
            self._left_state = GestureState.PINCH_OPEN
            self._left_close_count = 0
            self._left_release_count = 0
            self._left_cooldown_until_ms = 0
        elif left_dist is not None:
            if self._left_state == GestureState.COOLDOWN and now_ms < self._left_cooldown_until_ms:
                pass
            elif self._left_state == GestureState.COOLDOWN and now_ms >= self._left_cooldown_until_ms:
                self._left_state = GestureState.PINCH_OPEN
                self._left_close_count = 0
                self._left_release_count = 0
                self._left_cooldown_until_ms = 0

            if self._left_state == GestureState.PINCH_OPEN:
                if left_dist < self.config.pinch_close:
                    self._left_close_count += 1
                    if self._left_close_count >= self.config.confirm_frames:
                        self._left_state = GestureState.PINCH_PRESSED
                        self._left_release_count = 0
                        self._left_close_count = 0
                else:
                    self._left_close_count = 0

            elif self._left_state in (GestureState.PINCH_PRESSED, GestureState.PINCH_HOLD):
                if left_dist <= self.config.pinch_open:
                    self._left_release_count = 0
                    if self._left_state == GestureState.PINCH_PRESSED:
                        self._left_state = GestureState.PINCH_HOLD
                else:
                    self._left_release_count += 1
                    if self._left_release_count >= self.config.release_confirm_frames:
                        self._left_state = GestureState.COOLDOWN
                        self._left_cooldown_until_ms = now_ms + self.config.cooldown_ms
                        self._left_close_count = 0
                        self._left_release_count = 0
                        if self.config.emit_on_release:
                            if self._last_left_click_ms > 0 and now_ms - self._last_left_click_ms < 300:
                                should_double_click = True
                                self._last_left_click_ms = 0
                            else:
                                should_click = True
                                self._last_left_click_ms = now_ms

        # 2. Update Right State Machine
        should_right_click = False

        if self._left_state != GestureState.PINCH_OPEN:
            # Left click active, reset right click
            self._right_state = GestureState.PINCH_OPEN
            self._right_close_count = 0
            self._right_release_count = 0
            self._right_cooldown_until_ms = 0
        elif right_dist is not None:
            if self._right_state == GestureState.COOLDOWN and now_ms < self._right_cooldown_until_ms:
                pass
            elif self._right_state == GestureState.COOLDOWN and now_ms >= self._right_cooldown_until_ms:
                self._right_state = GestureState.PINCH_OPEN
                self._right_close_count = 0
                self._right_release_count = 0
                self._right_cooldown_until_ms = 0

            if self._right_state == GestureState.PINCH_OPEN:
                if right_dist < self.config.pinch_close:
                    self._right_close_count += 1
                    if self._right_close_count >= self.config.confirm_frames:
                        self._right_state = GestureState.PINCH_PRESSED
                        self._right_release_count = 0
                        self._right_close_count = 0
                else:
                    self._right_close_count = 0

            elif self._right_state in (GestureState.PINCH_PRESSED, GestureState.PINCH_HOLD):
                if right_dist <= self.config.pinch_open:
                    self._right_release_count = 0
                    if self._right_state == GestureState.PINCH_PRESSED:
                        self._right_state = GestureState.PINCH_HOLD
                else:
                    self._right_release_count += 1
                    if self._right_release_count >= self.config.release_confirm_frames:
                        self._right_state = GestureState.COOLDOWN
                        self._right_cooldown_until_ms = now_ms + self.config.cooldown_ms
                        self._right_close_count = 0
                        self._right_release_count = 0
                        if self.config.emit_on_release:
                            should_right_click = True

        return GestureResult(
            state=self._left_state,
            should_click=should_click,
            pinch_distance=left_dist,
            right_state=self._right_state,
            should_right_click=should_right_click,
            right_pinch_distance=right_dist,
            should_double_click=should_double_click,
        )

    def reset(self) -> None:
        self._left_state = GestureState.PINCH_OPEN
        self._left_close_count = 0
        self._left_release_count = 0
        self._left_cooldown_until_ms = 0

        self._right_state = GestureState.PINCH_OPEN
        self._right_close_count = 0
        self._right_release_count = 0
        self._right_cooldown_until_ms = 0

        if self.interlock:
            self.interlock.release(InterlockType.CLICK)


__all__ = ["GestureConfig", "GestureDetector", "GestureResult", "GestureState"]
