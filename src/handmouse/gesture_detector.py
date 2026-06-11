from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.types import FramePoint
from handmouse.interlock import InteractionInterlock, InterlockType
from handmouse.policy.gesture_policy import GestureCandidate, RiskClass
from handmouse.tracking.observation import HandObservation


@dataclass(frozen=True)
class GestureConfig:
    pinch_close_ratio: float = 0.5   # Ratio of pinch distance to palm span
    pinch_open_ratio: float = 0.7    # Ratio of pinch distance to palm span
    drag_start_ratio: float = 0.35   # Pinch-center movement relative to palm span
    confirm_frames: int = 2
    release_confirm_frames: int = 2
    cooldown_ms: int = 150
    emit_on_release: bool = True


class GestureState(Enum):
    PINCH_OPEN = auto()
    PINCH_PRESSED = auto()
    PINCH_HOLD = auto()
    COOLDOWN = auto()


class GestureDetector:
    def __init__(self, config: GestureConfig, interlock: InteractionInterlock | None = None) -> None:
        self.config = config
        self.interlock = interlock

        self._left_state = GestureState.PINCH_OPEN
        self._left_close_count = 0
        self._left_release_count = 0
        self._left_cooldown_until_ms = 0
        self._last_left_click_ms = 0
        self._left_press_center: FramePoint | None = None
        self._left_dragging = False

        self._right_state = GestureState.PINCH_OPEN
        self._right_close_count = 0
        self._right_release_count = 0
        self._right_cooldown_until_ms = 0

    def update(self, obs: HandObservation | None, now_ms: int) -> list[GestureCandidate]:
        if obs is None or not obs.image_landmarks or len(obs.image_landmarks) < 21:
            self.reset()
            return []

        # Calculate palm span
        index_mcp = obs.image_landmarks[5]
        pinky_mcp = obs.image_landmarks[17]
        palm_span = hypot(index_mcp.x - pinky_mcp.x, index_mcp.y - pinky_mcp.y)
        if palm_span == 0:
            palm_span = 1.0

        thumb = obs.image_landmarks[4]
        index = obs.image_landmarks[8]
        middle = obs.image_landmarks[12]

        left_dist = hypot(thumb.x - index.x, thumb.y - index.y)
        right_dist = hypot(thumb.x - middle.x, thumb.y - middle.y)
        left_center = FramePoint((thumb.x + index.x) * 0.5, (thumb.y + index.y) * 0.5)

        left_ratio = left_dist / palm_span
        right_ratio = right_dist / palm_span
        self.last_distance = left_ratio

        left_wants_active = (left_ratio < self.config.pinch_close_ratio or self._left_state != GestureState.PINCH_OPEN)
        right_wants_active = (right_ratio < self.config.pinch_close_ratio or self._right_state != GestureState.PINCH_OPEN)

        wants_active = left_wants_active or right_wants_active
        if wants_active:
            if self.interlock and not self.interlock.try_acquire(InterlockType.CLICK):
                self.reset()
                return []
        else:
            if self.interlock:
                self.interlock.release(InterlockType.CLICK)

        candidates = []

        # 1. Update Left State Machine
        if self._right_state != GestureState.PINCH_OPEN:
            self._left_state = GestureState.PINCH_OPEN
            self._left_close_count = 0
            self._left_release_count = 0
            self._left_cooldown_until_ms = 0
            self._left_press_center = None
            self._left_dragging = False
        else:
            if self._left_state == GestureState.COOLDOWN and now_ms < self._left_cooldown_until_ms:
                pass
            elif self._left_state == GestureState.COOLDOWN and now_ms >= self._left_cooldown_until_ms:
                self._left_state = GestureState.PINCH_OPEN
                self._left_close_count = 0
                self._left_release_count = 0
                self._left_cooldown_until_ms = 0
                self._left_press_center = None
                self._left_dragging = False

            if self._left_state == GestureState.PINCH_OPEN:
                if left_ratio < self.config.pinch_close_ratio:
                    self._left_close_count += 1
                    if self._left_close_count >= self.config.confirm_frames:
                        self._left_state = GestureState.PINCH_PRESSED
                        self._left_release_count = 0
                        self._left_close_count = 0
                        self._left_press_center = left_center
                        self._left_dragging = False
                else:
                    self._left_close_count = 0

            elif self._left_state in (GestureState.PINCH_PRESSED, GestureState.PINCH_HOLD):
                if left_ratio <= self.config.pinch_open_ratio:
                    self._left_release_count = 0
                    if self._left_state == GestureState.PINCH_PRESSED:
                        self._left_state = GestureState.PINCH_HOLD
                    if not self._left_dragging and self._left_press_center is not None:
                        moved = hypot(
                            left_center.x - self._left_press_center.x,
                            left_center.y - self._left_press_center.y,
                        )
                        if moved >= palm_span * self.config.drag_start_ratio:
                            self._left_dragging = True
                            candidates.append(
                                GestureCandidate("pinch", "drag_hold", "fire", 1.0, RiskClass.MEDIUM, True)
                            )
                else:
                    self._left_release_count += 1
                    if self._left_release_count >= self.config.release_confirm_frames:
                        self._left_state = GestureState.COOLDOWN
                        self._left_cooldown_until_ms = now_ms + self.config.cooldown_ms
                        self._left_close_count = 0
                        self._left_release_count = 0
                        was_dragging = self._left_dragging
                        self._left_press_center = None
                        self._left_dragging = False
                        if was_dragging:
                            candidates.append(
                                GestureCandidate("pinch", "drag_release", "fire", 1.0, RiskClass.MEDIUM, True)
                            )
                        if self.config.emit_on_release and not was_dragging:
                            if self._last_left_click_ms > 0 and now_ms - self._last_left_click_ms < 300:
                                candidates.append(GestureCandidate("pinch", "double_click", "fire", 1.0, RiskClass.MEDIUM, True))
                                self._last_left_click_ms = 0
                            else:
                                candidates.append(GestureCandidate("pinch", "click_left", "fire", 1.0, RiskClass.MEDIUM, True))
                                self._last_left_click_ms = now_ms

        # 2. Update Right State Machine
        if self._left_state != GestureState.PINCH_OPEN:
            self._right_state = GestureState.PINCH_OPEN
            self._right_close_count = 0
            self._right_release_count = 0
            self._right_cooldown_until_ms = 0
        else:
            if self._right_state == GestureState.COOLDOWN and now_ms < self._right_cooldown_until_ms:
                pass
            elif self._right_state == GestureState.COOLDOWN and now_ms >= self._right_cooldown_until_ms:
                self._right_state = GestureState.PINCH_OPEN
                self._right_close_count = 0
                self._right_release_count = 0
                self._right_cooldown_until_ms = 0

            if self._right_state == GestureState.PINCH_OPEN:
                if right_ratio < self.config.pinch_close_ratio:
                    self._right_close_count += 1
                    if self._right_close_count >= self.config.confirm_frames:
                        self._right_state = GestureState.PINCH_PRESSED
                        self._right_release_count = 0
                        self._right_close_count = 0
                else:
                    self._right_close_count = 0

            elif self._right_state in (GestureState.PINCH_PRESSED, GestureState.PINCH_HOLD):
                if right_ratio <= self.config.pinch_open_ratio:
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
                            candidates.append(GestureCandidate("pinch", "click_right", "fire", 1.0, RiskClass.MEDIUM, True))

        return candidates

    def reset(self) -> None:
        self._left_state = GestureState.PINCH_OPEN
        self._left_close_count = 0
        self._left_release_count = 0
        self._left_cooldown_until_ms = 0
        self._left_press_center = None
        self._left_dragging = False

        self._right_state = GestureState.PINCH_OPEN
        self._right_close_count = 0
        self._right_release_count = 0
        self._right_cooldown_until_ms = 0

        if self.interlock:
            self.interlock.release(InterlockType.CLICK)

__all__ = ["GestureConfig", "GestureDetector", "GestureState"]
