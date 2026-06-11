from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Any

from handmouse.tracking.observation import HandObservation, TrackingQuality

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
            if c.phase == "fire":
                if c.risk == RiskClass.HIGH and not quality.ok:
                    continue # block high risk if not quality ok
                
                intents.append(GestureIntent(
                    action=c.gesture,
                    risk=c.risk,
                    detector=c.detector,
                    committed=True,
                    payload=c.measurements
                ))
        return intents
