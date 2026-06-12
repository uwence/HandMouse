from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from handmouse.config import ShortcutConfig
from handmouse.types import FramePoint
from handmouse.tracking.observation import HandObservation
from handmouse.policy.gesture_policy import GestureCandidate, RiskClass


class ShortcutAction(Enum):
    SWIPE_LEFT = auto()
    SWIPE_RIGHT = auto()
    SWIPE_UP = auto()
    SWIPE_DOWN = auto()
    SWIPE_LEFT_PALM = auto()
    SWIPE_RIGHT_PALM = auto()


class ShortcutState(Enum):
    NO_HAND = auto()
    TRACKING = auto()
    DETECTED = auto()
    COOLDOWN = auto()


class ShortcutDetector:
    MIN_PALM_OPEN_MS = 120
    MIN_SWIPE_ELAPSED_MS = 80
    MIN_SWIPE_SPEED = 0.0008

    def __init__(self, config: ShortcutConfig) -> None:
        self.config = config
        self._anchor: FramePoint | None = None
        self._anchor_ms: int | None = None
        self._cooldown_until_ms = 0
        self._palm_was_open = False
        self._palm_open_since_ms: int | None = None

    def update(
        self,
        obs: HandObservation | None,
        now_ms: int,
        point: FramePoint | None,
        palm_open: bool = False,
        generic_pose_active: bool = False,
    ) -> list[GestureCandidate]:
        if obs is None or point is None:
            self.reset()
            return []

        if now_ms < self._cooldown_until_ms:
            return []

        if self._anchor is None or self._anchor_ms is None:
            self._set_anchor(point, now_ms, palm_open)
            return []

        self._palm_was_open = self._palm_was_open or palm_open
        if palm_open:
            if self._palm_open_since_ms is None:
                self._palm_open_since_ms = now_ms
        elif not self._palm_was_open:
            self._palm_open_since_ms = None

        elapsed_ms = now_ms - self._anchor_ms
        if elapsed_ms > self.config.max_duration_ms:
            self._set_anchor(point, now_ms, palm_open)
            return []

        dx = point.x - self._anchor.x
        dy = point.y - self._anchor.y
        distance = (dx * dx + dy * dy) ** 0.5
        palm_open_ms = 0
        if self._palm_open_since_ms is not None:
            palm_open_ms = now_ms - self._palm_open_since_ms
        palm_swipe_qualified = self._palm_was_open and palm_open_ms >= self.MIN_PALM_OPEN_MS

        if not generic_pose_active:
            if not palm_swipe_qualified:
                return []
            if abs(dx) < abs(dy):
                self._set_anchor(point, now_ms, palm_open)
                return []

        if distance >= self.config.min_distance:
            elapsed_for_speed = max(elapsed_ms, 1)
            if elapsed_ms < self.MIN_SWIPE_ELAPSED_MS or (distance / elapsed_for_speed) < self.MIN_SWIPE_SPEED:
                self._set_anchor(point, now_ms, palm_open)
                return []

        action = self._classify(dx, dy, palm_swipe_qualified)
        
        if action is None:
            return []

        if palm_swipe_qualified:
            if action == ShortcutAction.SWIPE_LEFT:
                action = ShortcutAction.SWIPE_LEFT_PALM
            elif action == ShortcutAction.SWIPE_RIGHT:
                action = ShortcutAction.SWIPE_RIGHT_PALM

        self._anchor = None
        self._anchor_ms = None
        self._palm_was_open = False
        self._palm_open_since_ms = None
        self._cooldown_until_ms = now_ms + self.config.cooldown_ms

        gesture_map = {
            ShortcutAction.SWIPE_LEFT: "swipe_left",
            ShortcutAction.SWIPE_RIGHT: "swipe_right",
            ShortcutAction.SWIPE_UP: "swipe_up",
            ShortcutAction.SWIPE_DOWN: "swipe_down",
            ShortcutAction.SWIPE_LEFT_PALM: "swipe_left_palm",
            ShortcutAction.SWIPE_RIGHT_PALM: "swipe_right_palm",
        }
        
        risk = RiskClass.HIGH if action in (ShortcutAction.SWIPE_LEFT_PALM, ShortcutAction.SWIPE_RIGHT_PALM) else RiskClass.MEDIUM

        return [GestureCandidate(
            detector="shortcut",
            gesture=gesture_map[action],
            phase="fire",
            confidence=1.0,
            risk=risk,
            exclusive=True,
            measurements={"dx": dx, "dy": dy}
        )]

    def reset(self) -> None:
        self._anchor = None
        self._anchor_ms = None
        self._palm_was_open = False
        self._palm_open_since_ms = None

    def _set_anchor(self, point: FramePoint, now_ms: int, palm_open: bool) -> None:
        self._anchor = point
        self._anchor_ms = now_ms
        self._palm_was_open = palm_open
        self._palm_open_since_ms = now_ms if palm_open else None

    def _classify(self, dx: float, dy: float, palm_was_open: bool) -> ShortcutAction | None:
        abs_x = abs(dx)
        abs_y = abs(dy)
        base_threshold = self.config.min_distance
        
        h_threshold = base_threshold * 1.5 if palm_was_open else base_threshold
        ratio = self.config.axis_ratio

        if abs_x >= h_threshold and abs_x >= abs_y * ratio:
            return ShortcutAction.SWIPE_RIGHT if dx > 0 else ShortcutAction.SWIPE_LEFT

        if abs_y >= base_threshold and abs_y >= abs_x * ratio:
            return ShortcutAction.SWIPE_DOWN if dy > 0 else ShortcutAction.SWIPE_UP

        return None


__all__ = [
    "ShortcutAction",
    "ShortcutDetector",
    "ShortcutState",
]
