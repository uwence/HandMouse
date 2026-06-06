from __future__ import annotations

from typing import Any

from handmouse.pointer_mapper import ScreenPoint


try:
    import pyautogui
except ModuleNotFoundError:
    pyautogui: Any | None = None
else:
    pyautogui.FAILSAFE = True


class MouseController:
    def __init__(self) -> None:
        self._control_enabled = False

    def set_control_enabled(self, enabled: bool) -> None:
        self._control_enabled = enabled

    def is_control_enabled(self) -> bool:
        return self._control_enabled

    def move(self, point: ScreenPoint | None) -> None:
        if not self._control_enabled or point is None:
            return

        backend = self._backend()
        backend.moveTo(point.x, point.y, duration=0)

    def left_click(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        backend.click(button="left")

    def _backend(self) -> Any:
        if pyautogui is None:
            raise RuntimeError("PyAutoGUI is required when mouse control is enabled.")

        pyautogui.FAILSAFE = True
        return pyautogui
