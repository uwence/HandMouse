from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Any

from handmouse.tracking.observation import HandObservation, TrackingQuality
import handmouse.config as config_module

class RiskClass(str, Enum):
    LOW = "low"         # pointer move, low-speed scroll
    MEDIUM = "medium"   # click, right click, back/forward
    HIGH = "high"       # Win+D, Task View, Alt-Tab, app/window switching

@dataclass(frozen=True)
class GestureCandidate:
    detector: str
    gesture: str
    phase: Literal["candidate", "armed", "hold", "release", "fire", "cancel"]
    confidence: float
    risk: RiskClass
    exclusive: bool
    measurements: dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True)
class GestureIntent:
    action: str
    risk: RiskClass
    detector: str
    committed: bool
    payload: dict[str, Any] = field(default_factory=dict)

class GesturePolicy:
    def evaluate(
        self,
        obs: HandObservation | None,
        quality: TrackingQuality,
        candidates: list[GestureCandidate],
        session_state: dict[str, Any],
    ) -> list[GestureIntent]:
        intents = []
        for c in candidates:
            if c.phase != "fire" and c.phase != "cancel":
                continue
            if not self._feature_enabled(c.gesture):
                continue
            if self._requires_explicit_confirm(c.gesture) and not c.measurements.get("explicit_confirm"):
                continue
            if self._requires_quality_ok(c.gesture) and not quality.ok:
                continue

            intents.append(GestureIntent(
                action=c.gesture,
                risk=c.risk,
                detector=c.detector,
                committed=True,
                payload=c.measurements
            ))
        return intents

    def _feature_enabled(self, action: str) -> bool:
        switches = config_module.ACTIVE_CONFIG.gesture_switches
        if action == "click_right":
            return switches.right_click
        if action == "double_click":
            return switches.double_click
        if action in {"drag_hold", "drag_release"}:
            return switches.drag_drop
        if action in {"task_view", "nav_left", "nav_right", "nav_up", "nav_down", "task_view_commit"}:
            return switches.alt_tab
        if action in {"swipe_left_palm", "swipe_right_palm"}:
            return switches.win_d
        return True

    @staticmethod
    def _requires_quality_ok(action: str) -> bool:
        return action not in {"drag_release", "task_view_cancel"}

    @staticmethod
    def _requires_explicit_confirm(action: str) -> bool:
        return action == "task_view_commit"
