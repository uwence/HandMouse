from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class EngagementState(Enum):
    IDLE = auto()
    ARMED = auto()
    ACTIVE = auto()
    COOLDOWN = auto()


@dataclass(frozen=True)
class EngagementConfig:
    activation_hotkey: str = "m"
    palm_hold_ms: int = 200
    cooldown_ms: int = 100
    missing_frames_to_idle: int = 15
    escape_hotkey: str = "q"


@dataclass(frozen=True)
class EngagementResult:
    is_active: bool
    state: EngagementState
    reason: str


class EngagementFSM:
    def __init__(self, config: EngagementConfig) -> None:
        self.config = config
        self._state = EngagementState.IDLE
        self._cooldown_started_at_ms: int | None = None
        self._missing_frames = 0

    @property
    def state(self) -> EngagementState:
        return self._state

    def update(
        self,
        *,
        hotkey_pressed: bool,
        palm_visible: bool,
        palm_hold_ms: int,
        hand_missing: bool,
        escape_requested: bool,
        now_ms: int,
    ) -> EngagementResult:
        if escape_requested:
            self.force_idle()
            return self._result(EngagementState.IDLE, False, "escape")

        if hotkey_pressed:
            if self._state == EngagementState.IDLE:
                self._state = EngagementState.ARMED
                self._missing_frames = 0
                return self._result(EngagementState.ARMED, False, "hotkey")

            self.force_idle()
            return self._result(EngagementState.IDLE, False, "hotkey")

        if self._state == EngagementState.COOLDOWN:
            if self._cooldown_started_at_ms is not None:
                elapsed_ms = now_ms - self._cooldown_started_at_ms
                if elapsed_ms >= self.config.cooldown_ms:
                    self.force_idle()
                    return self._result(EngagementState.IDLE, False, "cooldown_done")
            return self._result(EngagementState.COOLDOWN, False, "cooldown")

        if self._state == EngagementState.IDLE:
            if palm_visible and palm_hold_ms >= self.config.palm_hold_ms:
                self._state = EngagementState.ARMED
                self._missing_frames = 0
                return self._result(EngagementState.ARMED, False, "palm_hold")
            return self._result(EngagementState.IDLE, False, "idle")

        if self._state == EngagementState.ARMED:
            if not hand_missing:
                self._state = EngagementState.ACTIVE
                self._missing_frames = 0
                return self._result(EngagementState.ACTIVE, True, "active")
            return self._result(EngagementState.ARMED, False, "armed")

        if self._state == EngagementState.ACTIVE:
            if hand_missing:
                self._missing_frames += 1
                if self._missing_frames >= self.config.missing_frames_to_idle:
                    self._state = EngagementState.COOLDOWN
                    self._cooldown_started_at_ms = now_ms
                    self._missing_frames = 0
                    return self._result(EngagementState.COOLDOWN, False, "missing")
                return self._result(EngagementState.ACTIVE, True, "active")

            self._missing_frames = 0
            return self._result(EngagementState.ACTIVE, True, "active")

        return self._result(self._state, self._state == EngagementState.ACTIVE, "idle")

    def force_idle(self) -> None:
        self._state = EngagementState.IDLE
        self._cooldown_started_at_ms = None
        self._missing_frames = 0

    def reset(self) -> None:
        self.force_idle()

    @staticmethod
    def _result(state: EngagementState, is_active: bool, reason: str) -> EngagementResult:
        return EngagementResult(state=state, is_active=is_active, reason=reason)


__all__ = ["EngagementConfig", "EngagementFSM", "EngagementResult", "EngagementState"]
