from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from handmouse.config import ShortcutConfig
from handmouse.types import FramePoint


class ShortcutAction(Enum):
    SWIPE_LEFT = auto()
    SWIPE_RIGHT = auto()
    SWIPE_UP = auto()
    SWIPE_DOWN = auto()
    SWIPE_UP_VSIGN = auto()
    SWIPE_DOWN_VSIGN = auto()


class ShortcutState(Enum):
    NO_HAND = auto()
    TRACKING = auto()
    DETECTED = auto()
    COOLDOWN = auto()


@dataclass(frozen=True)
class ShortcutResult:
    state: ShortcutState
    action: ShortcutAction | None
    displacement_x: float | None
    displacement_y: float | None


class ShortcutDetector:
    def __init__(self, config: ShortcutConfig) -> None:
        self.config = config
        self._anchor: FramePoint | None = None
        self._anchor_ms: int | None = None
        self._cooldown_until_ms = 0
        self._vsign_was_open = False

    def update(self, point: FramePoint | None, now_ms: int, vsign_open: bool = False) -> ShortcutResult:
        if point is None:
            self.reset()
            return ShortcutResult(ShortcutState.NO_HAND, None, None, None)

        if now_ms < self._cooldown_until_ms:
            return ShortcutResult(ShortcutState.COOLDOWN, None, None, None)

        if self._anchor is None or self._anchor_ms is None:
            self._anchor = point
            self._anchor_ms = now_ms
            self._vsign_was_open = vsign_open
            return ShortcutResult(ShortcutState.TRACKING, None, 0.0, 0.0)

        # Record if vsign is open at any point during tracking
        self._vsign_was_open = self._vsign_was_open or vsign_open

        elapsed_ms = now_ms - self._anchor_ms
        if elapsed_ms > self.config.max_duration_ms:
            self._anchor = point
            self._anchor_ms = now_ms
            self._vsign_was_open = vsign_open
            return ShortcutResult(ShortcutState.TRACKING, None, 0.0, 0.0)

        dx = point.x - self._anchor.x
        dy = point.y - self._anchor.y
        action = self._classify(dx, dy)
        if action is None:
            return ShortcutResult(ShortcutState.TRACKING, None, dx, dy)

        if self._vsign_was_open:
            if action == ShortcutAction.SWIPE_DOWN:
                action = ShortcutAction.SWIPE_DOWN_VSIGN
            elif action == ShortcutAction.SWIPE_UP:
                action = ShortcutAction.SWIPE_UP_VSIGN

        self._anchor = None
        self._anchor_ms = None
        self._vsign_was_open = False
        self._cooldown_until_ms = now_ms + self.config.cooldown_ms
        return ShortcutResult(ShortcutState.DETECTED, action, dx, dy)

    def reset(self) -> None:
        self._anchor = None
        self._anchor_ms = None
        self._vsign_was_open = False

    def _classify(self, dx: float, dy: float) -> ShortcutAction | None:
        abs_x = abs(dx)
        abs_y = abs(dy)
        threshold = self.config.min_distance
        ratio = self.config.axis_ratio

        if abs_x >= threshold and abs_x >= abs_y * ratio:
            return ShortcutAction.SWIPE_RIGHT if dx > 0 else ShortcutAction.SWIPE_LEFT

        if abs_y >= threshold and abs_y >= abs_x * ratio:
            return ShortcutAction.SWIPE_DOWN if dy > 0 else ShortcutAction.SWIPE_UP

        return None


__all__ = [
    "ShortcutAction",
    "ShortcutDetector",
    "ShortcutResult",
    "ShortcutState",
]
