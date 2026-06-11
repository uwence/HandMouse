import pytest

from handmouse import mouse_controller
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.types import ScreenDelta, ScreenPoint


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
    monkeypatch.setattr(MouseController, "_dispatch_move", lambda self, p: self._move_pyautogui(p))
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
    monkeypatch.setattr(MouseController, "_dispatch_move_relative", lambda self, d: self._move_relative_pyautogui(d))
    backend = RecordingPyAutoGUI()
    monkeypatch.setattr(mouse_controller, "pyautogui", backend)
    controller = MouseController()
    controller.set_control_enabled(True)

    controller.move_relative(ScreenDelta(12, -8))

    assert backend.moves == [(12, -8, 0)]


def test_move_uses_windows_backend_when_platform_is_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows, move() must dispatch to the ctypes user32 backend instead of pyautogui."""
    calls: list[tuple] = []

    class FakeUser32:
        @staticmethod
        def SetCursorPos(x: int, y: int) -> None:
            calls.append(("SetCursorPos", x, y))

        @staticmethod
        def mouse_event(flags: int, dx: int, dy: int, _data: int, _extra: int) -> None:
            calls.append(("mouse_event", flags, dx, dy))

    class FakeWindll:
        user32 = FakeUser32

    fake_ctypes = type("ctypes", (), {"windll": FakeWindll()})
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)

    controller = MouseController()
    controller.set_control_enabled(True)
    controller.move(ScreenPoint(100, 200))

    assert ("SetCursorPos", 100, 200) in calls
    assert ("mouse_event", 0x0001, 0, 0) in calls


def test_move_relative_uses_windows_backend_when_platform_is_win32(monkeypatch: pytest.MonkeyPatch) -> None:
    """On Windows, move_relative() must dispatch to mouse_event(0x0001, dx, dy, 0, 0)."""
    calls: list[tuple] = []

    class FakeUser32:
        @staticmethod
        def mouse_event(flags: int, dx: int, dy: int, _data: int, _extra: int) -> None:
            calls.append((flags, dx, dy))

    class FakeWindll:
        user32 = FakeUser32

    fake_ctypes = type("ctypes", (), {"windll": FakeWindll()})
    monkeypatch.setitem(__import__("sys").modules, "ctypes", fake_ctypes)

    controller = MouseController()
    controller.set_control_enabled(True)
    controller.move_relative(ScreenDelta(12, -8))

    assert calls == [(0x0001, 12, -8)]
