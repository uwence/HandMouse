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

@dataclass(frozen=True)
class GestureDecision:
    action: str
    risk: RiskClass
    detector: str
    committed: bool
    payload: dict[str, Any] = field(default_factory=dict)

class GesturePolicy:
    def __init__(
        self,
        high_risk_cooldown_ms: int = 500,
        explicit_confirm_required: bool = True,
    ) -> None:
        self.high_risk_cooldown_ms = high_risk_cooldown_ms
        self.explicit_confirm_required = explicit_confirm_required
        self._last_high_risk_ms = -1

    def evaluate(
        self,
        obs: HandObservation | None,
        quality: TrackingQuality,
        candidates: list[GestureCandidate],
        session_state: dict[str, Any],
    ) -> list[GestureDecision]:
        decisions = []
        now_ms = int(session_state.get("now_ms", 0))
        for c in candidates:
            if c.phase != "fire" and c.phase != "cancel":
                continue
            decision = self.decide_candidate(c, quality, {"now_ms": now_ms, **session_state})
            decisions.append(decision)
            if decision.committed and c.risk == RiskClass.HIGH and decision.action != "task_view_cancel":
                self._last_high_risk_ms = now_ms
        return decisions

    def decide_candidate(
        self,
        candidate: GestureCandidate,
        quality: TrackingQuality,
        session_state: dict[str, Any],
    ) -> GestureDecision:
        now_ms = int(session_state.get("now_ms", 0))
        blocked_by = self._blocked_reason(candidate, quality, now_ms)
        payload = {**candidate.measurements}
        if blocked_by is not None:
            payload["blocked_by"] = blocked_by
        return GestureDecision(
            action=candidate.gesture,
            risk=candidate.risk,
            detector=candidate.detector,
            committed=blocked_by is None,
            payload=payload,
        )

    def _blocked_reason(
        self,
        candidate: GestureCandidate,
        quality: TrackingQuality,
        now_ms: int,
    ) -> str | None:
        if not self._feature_enabled(candidate.gesture):
            return "feature_disabled"
        if self._requires_explicit_confirm(candidate.gesture) and not candidate.measurements.get("explicit_confirm"):
            return "explicit_confirm_required"
        if self._requires_quality_ok(candidate.gesture) and not quality.ok:
            return "quality_gate"
        if (
            candidate.risk == RiskClass.HIGH
            and self._cooldown_applies(candidate.gesture)
            and candidate.gesture != "task_view_cancel"
            and self._last_high_risk_ms >= 0
            and (now_ms - self._last_high_risk_ms) < self.high_risk_cooldown_ms
        ):
            return "cooldown"
        return None

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

    def _requires_explicit_confirm(self, action: str) -> bool:
        if not self.explicit_confirm_required:
            return False
        return action in {
            "task_view",
            "task_view_commit",
            "swipe_left_palm",
            "swipe_right_palm",
        }

    @staticmethod
    def _cooldown_applies(action: str) -> bool:
        return action in {
            "task_view",
            "swipe_left_palm",
            "swipe_right_palm",
        }
