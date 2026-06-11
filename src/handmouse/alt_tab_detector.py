from __future__ import annotations

from enum import Enum, auto
from typing import Any

from handmouse.types import FramePoint
from handmouse.policy.gesture_policy import GestureCandidate, RiskClass


class AltTabState(Enum):
    INACTIVE = auto()
    ARMING = auto()
    ACTIVE = auto()


class AltTabDetector:
    def __init__(
        self,
        arming_time_ms: int = 350,
        nav_threshold: float = 0.08,
        cooldown_ms: int = 400,
        confirm_pinch_ratio: float = 0.45,
    ) -> None:
        self.arming_time_ms = arming_time_ms
        self.nav_threshold = nav_threshold
        self.cooldown_ms = cooldown_ms
        self.confirm_pinch_ratio = confirm_pinch_ratio

        self.state = AltTabState.INACTIVE
        self._arming_start_ms = 0
        self._anchor_x = 0.0
        self._anchor_y = 0.0
        self._next_nav_ms = 0

    def update(self, landmarks: list[FramePoint] | None, now_ms: int) -> list[GestureCandidate]:
        is_pose = self._is_alt_tab_pose(landmarks)
        palm_center = self._palm_center(landmarks) if landmarks else None
        
        candidates = []

        if self.state == AltTabState.INACTIVE:
            if is_pose:
                self.state = AltTabState.ARMING
                self._arming_start_ms = now_ms
                candidates.append(GestureCandidate(
                    detector="task_view",
                    gesture="task_view",
                    phase="candidate",
                    confidence=1.0,
                    risk=RiskClass.HIGH,
                    exclusive=False
                ))

        elif self.state == AltTabState.ARMING:
            if is_pose:
                if now_ms - self._arming_start_ms >= self.arming_time_ms:
                    self.state = AltTabState.ACTIVE
                    self._anchor_x = palm_center.x if palm_center else 0.5
                    self._anchor_y = palm_center.y if palm_center else 0.5
                    self._next_nav_ms = now_ms + self.cooldown_ms
                    
                    candidates.append(GestureCandidate(
                        detector="task_view",
                        gesture="task_view",
                        phase="fire",
                        confidence=1.0,
                        risk=RiskClass.HIGH,
                        exclusive=True
                    ))
                else:
                    candidates.append(GestureCandidate(
                        detector="task_view",
                        gesture="task_view",
                        phase="armed",
                        confidence=1.0,
                        risk=RiskClass.HIGH,
                        exclusive=False
                    ))
            else:
                self.state = AltTabState.INACTIVE
                candidates.append(GestureCandidate(
                    detector="task_view",
                    gesture="task_view",
                    phase="cancel",
                    confidence=1.0,
                    risk=RiskClass.HIGH,
                    exclusive=False
                ))

        elif self.state == AltTabState.ACTIVE:
            if is_pose:
                if self._has_confirm_pinch(landmarks):
                    self.state = AltTabState.INACTIVE
                    candidates.append(GestureCandidate(
                        detector="task_view",
                        gesture="task_view_commit",
                        phase="fire",
                        confidence=1.0,
                        risk=RiskClass.HIGH,
                        exclusive=True,
                        measurements={"explicit_confirm": 1.0},
                    ))
                    return candidates

                candidates.append(GestureCandidate(
                    detector="task_view",
                    gesture="task_view",
                    phase="hold",
                    confidence=1.0,
                    risk=RiskClass.HIGH,
                    exclusive=True
                ))
                if palm_center and now_ms >= self._next_nav_ms:
                    dx = palm_center.x - self._anchor_x
                    dy = palm_center.y - self._anchor_y
                    
                    if abs(dx) > self.nav_threshold or abs(dy) > self.nav_threshold:
                        nav_action = None
                        if abs(dx) > abs(dy):
                            if dx > self.nav_threshold:
                                nav_action = "nav_right"
                                self._anchor_x = palm_center.x
                            elif dx < -self.nav_threshold:
                                nav_action = "nav_left"
                                self._anchor_x = palm_center.x
                        else:
                            if dy > self.nav_threshold:
                                nav_action = "nav_down"
                                self._anchor_y = palm_center.y
                            elif dy < -self.nav_threshold:
                                nav_action = "nav_up"
                                self._anchor_y = palm_center.y
                                
                        if nav_action:
                            candidates.append(GestureCandidate(
                                detector="task_view",
                                gesture=nav_action,
                                phase="fire",
                                confidence=1.0,
                                risk=RiskClass.HIGH,
                                exclusive=True
                            ))
                            self._next_nav_ms = now_ms + self.cooldown_ms
            else:
                self.state = AltTabState.INACTIVE
                candidates.append(GestureCandidate(
                    detector="task_view",
                    gesture="task_view_cancel",
                    phase="cancel",
                    confidence=1.0,
                    risk=RiskClass.HIGH,
                    exclusive=True
                ))

        return candidates

    def reset(self) -> None:
        self.state = AltTabState.INACTIVE

    def _is_alt_tab_pose(self, landmarks: list[FramePoint] | None) -> bool:
        if not landmarks or len(landmarks) < 21:
            return False

        wrist = landmarks[0]
        def dist(a: FramePoint, b: FramePoint) -> float:
            return ((a.x - b.x) ** 2 + (a.y - b.y) ** 2) ** 0.5

        # Check extended fingers: Index (8, 6), Middle (12, 10), Ring (16, 14)
        extended = 0
        for tip_i, pip_i in ((8, 6), (12, 10), (16, 14)):
            if dist(landmarks[tip_i], wrist) > dist(landmarks[pip_i], wrist):
                extended += 1

        # Check curled fingers: Pinky (20, 18)
        pinky_curled = dist(landmarks[20], wrist) < dist(landmarks[18], wrist)

        return extended == 3 and pinky_curled

    def _palm_center(self, landmarks: list[FramePoint]) -> FramePoint:
        palm_indices = (0, 5, 9, 13, 17)
        return FramePoint(
            sum(landmarks[i].x for i in palm_indices) / len(palm_indices),
            sum(landmarks[i].y for i in palm_indices) / len(palm_indices)
        )

    def _has_confirm_pinch(self, landmarks: list[FramePoint] | None) -> bool:
        if not landmarks or len(landmarks) < 21:
            return False

        thumb = landmarks[4]
        index = landmarks[8]
        index_mcp = landmarks[5]
        pinky_mcp = landmarks[17]
        palm_span = ((index_mcp.x - pinky_mcp.x) ** 2 + (index_mcp.y - pinky_mcp.y) ** 2) ** 0.5
        if palm_span <= 0:
            return False

        pinch_distance = ((thumb.x - index.x) ** 2 + (thumb.y - index.y) ** 2) ** 0.5
        return (pinch_distance / palm_span) <= self.confirm_pinch_ratio


__all__ = ["AltTabDetector", "AltTabState"]
