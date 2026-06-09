from __future__ import annotations

from enum import Enum, auto
from typing import Any

from handmouse.types import FramePoint


try:
    import pyautogui
except ModuleNotFoundError:
    pyautogui: Any | None = None


class AltTabState(Enum):
    INACTIVE = auto()
    ARMING = auto()
    ACTIVE = auto()


class AltTabDetector:
    def __init__(self, arming_time_ms: int = 350, nav_threshold: float = 0.08, cooldown_ms: int = 400) -> None:
        self.arming_time_ms = arming_time_ms
        self.nav_threshold = nav_threshold
        self.cooldown_ms = cooldown_ms

        self.state = AltTabState.INACTIVE
        self._arming_start_ms = 0
        self._anchor_x = 0.0
        self._anchor_y = 0.0
        self._next_nav_ms = 0

    def update(self, landmarks: list[FramePoint] | None, now_ms: int) -> tuple[AltTabState, bool]:
        """Updates AltTabState and returns (current_state, is_alt_held)."""
        is_pose = self._is_alt_tab_pose(landmarks)
        palm_center = self._palm_center(landmarks) if landmarks else None

        if self.state == AltTabState.INACTIVE:
            if is_pose:
                self.state = AltTabState.ARMING
                self._arming_start_ms = now_ms
            return self.state, False

        elif self.state == AltTabState.ARMING:
            if is_pose:
                if now_ms - self._arming_start_ms >= self.arming_time_ms:
                    self.state = AltTabState.ACTIVE
                    self._anchor_x = palm_center.x if palm_center else 0.5
                    self._anchor_y = palm_center.y if palm_center else 0.5
                    self._next_nav_ms = now_ms + self.cooldown_ms
                    self._press_win_tab()
                    return self.state, True
                return self.state, False
            else:
                self.state = AltTabState.INACTIVE
                return self.state, False

        elif self.state == AltTabState.ACTIVE:
            if is_pose:
                if palm_center and now_ms >= self._next_nav_ms:
                    dx = palm_center.x - self._anchor_x
                    dy = palm_center.y - self._anchor_y
                    
                    if abs(dx) > self.nav_threshold or abs(dy) > self.nav_threshold:
                        if abs(dx) > abs(dy):
                            if dx > self.nav_threshold:
                                self._press_nav("right")
                                self._anchor_x = palm_center.x
                            elif dx < -self.nav_threshold:
                                self._press_nav("left")
                                self._anchor_x = palm_center.x
                        else:
                            if dy > self.nav_threshold:
                                self._press_nav("down")
                                self._anchor_y = palm_center.y
                            elif dy < -self.nav_threshold:
                                self._press_nav("up")
                                self._anchor_y = palm_center.y
                        
                        self._next_nav_ms = now_ms + self.cooldown_ms
                return self.state, True
            else:
                self.state = AltTabState.INACTIVE
                self._submit_selection()
                return self.state, False

        return self.state, False

    def reset(self) -> None:
        if self.state == AltTabState.ACTIVE:
            self._submit_selection()
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

    def _press_win_tab(self) -> None:
        if pyautogui is None:
            return
        try:
            pyautogui.hotkey("win", "tab")
        except Exception:
            pass

    def _press_nav(self, key: str) -> None:
        if pyautogui is None:
            return
        try:
            pyautogui.press(key)
        except Exception:
            pass

    def _submit_selection(self) -> None:
        if pyautogui is None:
            return
        try:
            pyautogui.press("enter")
        except Exception:
            pass


__all__ = ["AltTabDetector", "AltTabState"]
