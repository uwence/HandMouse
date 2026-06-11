from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import pyautogui

from handmouse.policy.gesture_policy import GestureIntent

@dataclass(frozen=True)
class ActionDispatch:
    action: str
    executed: bool
    blocked_by: str | None
    latency_ms: int

class ActionRouter:
    def __init__(self, mouse_controller: Any, shortcut_controller: Any):
        self.mouse = mouse_controller
        self.shortcut = shortcut_controller
        self._drag_active = False
        self._task_view_open = False
        
    def dispatch(
        self,
        intents: list[GestureIntent],
        session_state: dict[str, Any],
    ) -> list[ActionDispatch]:
        results = []
        for intent in intents:
            if not intent.committed:
                continue
                
            executed = False
            blocked_by = None
            
            if intent.action == "click_left":
                self.mouse.left_click()
                executed = True
            elif intent.action == "double_click":
                self.mouse.double_click()
                executed = True
            elif intent.action == "click_right":
                self.mouse.right_click()
                executed = True
            elif intent.action == "drag_hold":
                if not self._drag_active:
                    self.mouse.left_down()
                    self._drag_active = True
                    executed = True
            elif intent.action == "drag_release":
                if self._drag_active:
                    self.mouse.left_up()
                    self._drag_active = False
                    executed = True
            elif intent.action == "task_view":
                if not self._task_view_open:
                    pyautogui.hotkey("win", "tab")
                    self._task_view_open = True
                    executed = True
            elif intent.action == "nav_left":
                if self._task_view_open:
                    pyautogui.press("left")
                    executed = True
            elif intent.action == "nav_right":
                if self._task_view_open:
                    pyautogui.press("right")
                    executed = True
            elif intent.action == "nav_up":
                if self._task_view_open:
                    pyautogui.press("up")
                    executed = True
            elif intent.action == "nav_down":
                if self._task_view_open:
                    pyautogui.press("down")
                    executed = True
            elif intent.action == "task_view_commit":
                if self._task_view_open:
                    pyautogui.press("enter")
                    self._task_view_open = False
                    executed = True
            elif intent.action == "task_view_cancel":
                if self._task_view_open:
                    pyautogui.press("esc")
                    self._task_view_open = False
                    executed = True
            elif intent.action == "scroll":
                self.shortcut.scroll(int(intent.payload.get("delta", 0)))
                executed = True
            elif intent.action.startswith("swipe_"):
                from handmouse.shortcut_detector import ShortcutAction
                action_map = {
                    "swipe_left": ShortcutAction.SWIPE_LEFT,
                    "swipe_right": ShortcutAction.SWIPE_RIGHT,
                    "swipe_up": ShortcutAction.SWIPE_UP,
                    "swipe_down": ShortcutAction.SWIPE_DOWN,
                    "swipe_left_palm": ShortcutAction.SWIPE_LEFT_PALM,
                    "swipe_right_palm": ShortcutAction.SWIPE_RIGHT_PALM,
                }
                mapped_action = action_map.get(intent.action)
                if mapped_action:
                    self.shortcut.execute(mapped_action)
                    executed = True
            
            results.append(ActionDispatch(
                action=intent.action,
                executed=executed,
                blocked_by=blocked_by,
                latency_ms=0
            ))
            try:
                from handmouse.telemetry.writer import log_event
                log_event("action_dispatch", {
                    "action": intent.action,
                    "executed": executed,
                    "blocked_by": blocked_by,
                })
            except Exception:
                pass
            
        return results
