from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MoveModeState(Enum):
    NEUTRAL = auto()
    ARMED = auto()
    ACTIVE = auto()


@dataclass(frozen=True)
class MoveModeConfig:
    arm_dwell_ms: int = 150
    pose_loss_grace_ms: int = 80


@dataclass(frozen=True)
class MoveModeResult:
    state: MoveModeState
    movement_enabled: bool
    move_pose: bool
    clutch_down: bool


class MoveModeController:
    def __init__(self, config: MoveModeConfig) -> None:
        self.config = config
        self._state = MoveModeState.NEUTRAL
        self._armed_since_ms: int | None = None

    def update(self, *, clutch_down: bool, move_pose: bool, now_ms: int) -> MoveModeResult:
        if not clutch_down:
            self.reset()
            return MoveModeResult(
                state=MoveModeState.NEUTRAL,
                movement_enabled=False,
                move_pose=move_pose,
                clutch_down=clutch_down,
            )

        if self._state is MoveModeState.NEUTRAL:
            if move_pose:
                self._state = MoveModeState.ARMED
                self._armed_since_ms = now_ms
            return MoveModeResult(
                state=self._state,
                movement_enabled=False,
                move_pose=move_pose,
                clutch_down=clutch_down,
            )

        if self._state is MoveModeState.ARMED:
            if not move_pose:
                self._state = MoveModeState.NEUTRAL
                self._armed_since_ms = None
                return MoveModeResult(
                    state=MoveModeState.NEUTRAL,
                    movement_enabled=False,
                    move_pose=move_pose,
                    clutch_down=clutch_down,
                )

            if self._armed_since_ms is None:
                self._armed_since_ms = now_ms
            if now_ms - self._armed_since_ms >= self.config.arm_dwell_ms:
                self._state = MoveModeState.ACTIVE
                return MoveModeResult(
                    state=MoveModeState.ACTIVE,
                    movement_enabled=True,
                    move_pose=move_pose,
                    clutch_down=clutch_down,
                )

            return MoveModeResult(
                state=MoveModeState.ARMED,
                movement_enabled=False,
                move_pose=move_pose,
                clutch_down=clutch_down,
            )

        if not move_pose:
            self._state = MoveModeState.ARMED
            self._armed_since_ms = now_ms
            return MoveModeResult(
                state=MoveModeState.ARMED,
                movement_enabled=False,
                move_pose=move_pose,
                clutch_down=clutch_down,
            )

        return MoveModeResult(
            state=MoveModeState.ACTIVE,
            movement_enabled=True,
            move_pose=move_pose,
            clutch_down=clutch_down,
        )

    def reset(self) -> None:
        self._state = MoveModeState.NEUTRAL
        self._armed_since_ms = None


__all__ = [
    "MoveModeConfig",
    "MoveModeController",
    "MoveModeResult",
    "MoveModeState",
]
