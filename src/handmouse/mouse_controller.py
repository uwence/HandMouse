from __future__ import annotations

from typing import Any

from handmouse.types import ScreenDelta, ScreenPoint


try:
    import pyautogui
except ModuleNotFoundError:
    pyautogui: Any | None = None
else:
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0


class MouseFailsafeTriggered(RuntimeError):
    """Raised when PyAutoGUI aborts because the pointer is in a screen corner."""


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
        try:
            backend.moveTo(point.x, point.y, duration=0)
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def move_relative(self, delta: ScreenDelta | None) -> None:
        if not self._control_enabled or delta is None:
            return

        backend = self._backend()
        try:
            backend.moveRel(delta.dx, delta.dy, duration=0)
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def left_click(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        try:
            backend.click(button="left")
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def right_click(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        try:
            backend.click(button="right")
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def double_click(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        try:
            backend.doubleClick(button="left")
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def left_down(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        try:
            backend.mouseDown(button="left")
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def left_up(self) -> None:
        if not self._control_enabled:
            return

        backend = self._backend()
        try:
            backend.mouseUp(button="left")
        except Exception as exc:
            if self._is_failsafe_exception(exc):
                raise MouseFailsafeTriggered(
                    "PyAutoGUI failsafe triggered; disabling real mouse control."
                ) from exc
            raise

    def _backend(self) -> Any:
        if pyautogui is None:
            raise RuntimeError("PyAutoGUI is required when mouse control is enabled.")

        pyautogui.FAILSAFE = False
        return pyautogui

    @staticmethod
    def _is_failsafe_exception(exc: Exception) -> bool:
        if pyautogui is not None:
            failsafe_type = getattr(pyautogui, "FailSafeException", None)
            if failsafe_type is not None and isinstance(exc, failsafe_type):
                return True

        return exc.__class__.__name__ == "FailSafeException"


__all__ = ["MouseController", "MouseFailsafeTriggered"]
