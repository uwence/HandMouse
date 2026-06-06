import pytest

from handmouse import mouse_controller
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.pointer_mapper import ScreenPoint


class FakeFailSafeException(Exception):
    pass


class FakePyAutoGUI:
    FAILSAFE = False
    FailSafeException = FakeFailSafeException

    def moveTo(self, x: int, y: int, duration: int = 0) -> None:
        raise self.FailSafeException("corner")

    def click(self, button: str = "left") -> None:
        raise self.FailSafeException("corner")


def test_move_wraps_pyautogui_failsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mouse_controller, "pyautogui", FakePyAutoGUI())
    controller = MouseController()
    controller.set_control_enabled(True)

    with pytest.raises(MouseFailsafeTriggered):
        controller.move(ScreenPoint(0, 0))


def test_click_wraps_pyautogui_failsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mouse_controller, "pyautogui", FakePyAutoGUI())
    controller = MouseController()
    controller.set_control_enabled(True)

    with pytest.raises(MouseFailsafeTriggered):
        controller.left_click()
