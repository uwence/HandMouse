from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from handmouse.pose_detector import PoseDetector
from handmouse.tracking.observation import HandObservation


class BimanualGateState(Enum):
    IDLE = auto()
    ARMED = auto()
    ACTIVE = auto()
    SUSPENDED = auto()


@dataclass(frozen=True)
class BimanualGateResult:
    state: BimanualGateState
    gate_active: bool
    pointer_frozen: bool


class BimanualGate:
    def __init__(
        self,
        open_hold_ms: int = 250,
        open_stable_frames: int = 4,
        suspend_grace_ms: int = 150,
        idle_grace_ms: int = 500,
    ) -> None:
        self.open_hold_ms = open_hold_ms
        self.open_stable_frames = open_stable_frames
        self.suspend_grace_ms = suspend_grace_ms
        self.idle_grace_ms = idle_grace_ms

        self._state = BimanualGateState.IDLE
        self._open_since_ms: int | None = None
        self._open_frame_count: int = 0
        self._mode_last_seen_ms: int | None = None  # last time mode was present

    def update(
        self,
        mode_obs: HandObservation | None,
        pointer_obs: HandObservation | None,
        now_ms: int,
        pointer_stable: bool = True,
    ) -> BimanualGateResult:
        mode_palm_open = mode_obs is not None and PoseDetector.is_palm_open(mode_obs)
        mode_fist = mode_obs is not None and PoseDetector.is_fist(mode_obs)
        mode_present = mode_obs is not None

        if mode_present:
            self._mode_last_seen_ms = now_ms

        if self._state == BimanualGateState.IDLE:
            self._state = self._update_idle(mode_palm_open, now_ms)
        elif self._state == BimanualGateState.ARMED:
            self._state = self._update_armed(mode_palm_open, mode_present, pointer_obs, mode_fist, pointer_stable)
        elif self._state == BimanualGateState.ACTIVE:
            self._state = self._update_active(mode_present, mode_palm_open, mode_fist, now_ms)
        elif self._state == BimanualGateState.SUSPENDED:
            self._state = self._update_suspended(mode_present, mode_palm_open, mode_fist, now_ms)

        gate_active = self._state == BimanualGateState.ACTIVE
        # Mode-hand fist = explicit pointer lock: freeze the cursor in place so
        # the pointer hand can click/right-click a small target without drift.
        pointer_frozen = gate_active and mode_fist

        return BimanualGateResult(
            state=self._state,
            gate_active=gate_active,
            pointer_frozen=pointer_frozen,
        )

    def reset(self) -> None:
        self._state = BimanualGateState.IDLE
        self._open_since_ms = None
        self._open_frame_count = 0
        self._mode_last_seen_ms = None

    def _update_idle(self, mode_palm_open: bool, now_ms: int) -> BimanualGateState:
        if not mode_palm_open:
            self._open_since_ms = None
            self._open_frame_count = 0
            return BimanualGateState.IDLE
        if self._open_since_ms is None:
            self._open_since_ms = now_ms
            self._open_frame_count = 1
        else:
            self._open_frame_count += 1
        hold_ms = now_ms - self._open_since_ms
        # open_hold_ms==0 means "arm immediately" (bypass stable_frames check)
        if self.open_hold_ms == 0 or (hold_ms >= self.open_hold_ms and self._open_frame_count >= self.open_stable_frames):
            self._open_since_ms = None
            self._open_frame_count = 0
            return BimanualGateState.ARMED
        return BimanualGateState.IDLE

    def _update_armed(
        self,
        mode_palm_open: bool,
        mode_present: bool,
        pointer_obs: HandObservation | None,
        mode_fist: bool = False,
        pointer_stable: bool = True,
    ) -> BimanualGateState:
        if not mode_present:
            return BimanualGateState.IDLE
        # In ARMED, only OPEN hand maintains or advances; FIST or other closes gate
        if not mode_palm_open:
            return BimanualGateState.IDLE
        if pointer_obs is not None and pointer_stable:
            return BimanualGateState.ACTIVE
        return BimanualGateState.ARMED

    def _update_active(
        self,
        mode_present: bool,
        mode_palm_open: bool,
        mode_fist: bool,
        now_ms: int,
    ) -> BimanualGateState:
        if mode_present and (mode_palm_open or mode_fist):
            return BimanualGateState.ACTIVE
        if not mode_present and self._mode_last_seen_ms is not None:
            lost_ms = now_ms - self._mode_last_seen_ms
            if lost_ms > self.idle_grace_ms:
                return BimanualGateState.IDLE
            if lost_ms > self.suspend_grace_ms:
                return BimanualGateState.SUSPENDED
            return BimanualGateState.ACTIVE
        # mode_present but neither open nor fist → IDLE
        return BimanualGateState.IDLE

    def _update_suspended(
        self,
        mode_present: bool,
        mode_palm_open: bool,
        mode_fist: bool,
        now_ms: int,
    ) -> BimanualGateState:
        if mode_present:
            # Only restore ACTIVE on a recognised gate pose; bare presence is not enough
            if mode_palm_open or mode_fist:
                return BimanualGateState.ACTIVE
            return BimanualGateState.IDLE
        if self._mode_last_seen_ms is not None:
            lost_ms = now_ms - self._mode_last_seen_ms
            if lost_ms > self.idle_grace_ms:
                return BimanualGateState.IDLE
        return BimanualGateState.SUSPENDED


__all__ = ["BimanualGate", "BimanualGateResult", "BimanualGateState"]
