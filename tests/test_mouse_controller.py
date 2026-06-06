import pytest

from handmouse import mouse_controller
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.pointer_mapper import ScreenDelta, ScreenPoint


class FakeFailSafeException(Exception):
    pass


class FakePyAutoGUI:
    FAILSAFE = False
    FailSafeException = FakeFailSafeException

    def moveTo(self, x: int, y: int, duration: int = 0) -> None:
        raise self.FailSafeException("corner")

    def click(self, button: str = "left") -> None:
        raise self.FailSafeException("corner")


class RecordingPyAutoGUI:
    FAILSAFE = False

    def __init__(self) -> None:
        self.moves: list[tuple[int, int, int]] = []

    def moveRel(self, dx: int, dy: int, duration: int = 0) -> None:
        self.moves.append((dx, dy, duration))


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


def test_move_relative_uses_relative_backend_call(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = RecordingPyAutoGUI()
    monkeypatch.setattr(mouse_controller, "pyautogui", backend)
    controller = MouseController()
    controller.set_control_enabled(True)

    controller.move_relative(ScreenDelta(12, -8))

    assert backend.moves == [(12, -8, 0)]
