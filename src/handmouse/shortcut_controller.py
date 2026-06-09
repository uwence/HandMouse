from __future__ import annotations

from typing import Any

from handmouse.shortcut_detector import ShortcutAction


try:
    import pyautogui
    pyautogui.PAUSE = 0
except ModuleNotFoundError:
    pyautogui: Any | None = None


class ShortcutController:
    ARROW_PRESS_REPEATS = 4
    SCROLL_AMOUNT = 20

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
            self._press_repeatedly(backend, "left")
        elif action == ShortcutAction.SWIPE_RIGHT:
            self._press_repeatedly(backend, "right")
        elif action == ShortcutAction.SWIPE_UP:
            backend.scroll(self.SCROLL_AMOUNT)
        elif action == ShortcutAction.SWIPE_DOWN:
            backend.scroll(-self.SCROLL_AMOUNT)
        elif action in (ShortcutAction.SWIPE_LEFT_PALM, ShortcutAction.SWIPE_RIGHT_PALM):
            backend.hotkey("win", "d")

    def scroll(self, amount: int) -> None:
        if not self._enabled or amount == 0:
            return

        self._backend().scroll(amount)

    def _backend(self) -> Any:
        if pyautogui is None:
            raise RuntimeError("PyAutoGUI is required to execute gesture shortcuts.")

        return pyautogui

    def _press_repeatedly(self, backend: Any, key: str) -> None:
        for _ in range(self.ARROW_PRESS_REPEATS):
            backend.press(key)


__all__ = ["ShortcutController"]
