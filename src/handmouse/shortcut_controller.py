from __future__ import annotations

from typing import Any

from handmouse.shortcut_detector import ShortcutAction


try:
    import pyautogui
except ModuleNotFoundError:
    pyautogui: Any | None = None


class ShortcutController:
    def __init__(self) -> None:
        self._enabled = False

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled

    def is_enabled(self) -> bool:
        return self._enabled

    def execute(self, action: ShortcutAction | None) -> None:
        if not self._enabled or action is None:
            return

        backend = self._backend()
        if action == ShortcutAction.SWIPE_LEFT:
            backend.press("left")
        elif action == ShortcutAction.SWIPE_RIGHT:
            backend.press("right")
        elif action == ShortcutAction.SWIPE_UP:
            backend.scroll(5)
        elif action == ShortcutAction.SWIPE_DOWN:
            backend.scroll(-5)

    def _backend(self) -> Any:
        if pyautogui is None:
            raise RuntimeError("PyAutoGUI is required to execute gesture shortcuts.")

        return pyautogui


__all__ = ["ShortcutController"]
