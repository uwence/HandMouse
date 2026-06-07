from handmouse import shortcut_controller
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutAction


class RecordingPyAutoGUI:
    def __init__(self) -> None:
        self.presses: list[str] = []
        self.scrolls: list[int] = []

    def press(self, key: str) -> None:
        self.presses.append(key)

    def scroll(self, amount: int) -> None:
        self.scrolls.append(amount)


def test_execute_noops_when_disabled(monkeypatch) -> None:
    backend = RecordingPyAutoGUI()
    monkeypatch.setattr(shortcut_controller, "pyautogui", backend)
    controller = ShortcutController()

    controller.execute(ShortcutAction.SWIPE_RIGHT)

    assert backend.presses == []
    assert backend.scrolls == []


def test_horizontal_swipes_press_arrow_keys(monkeypatch) -> None:
    backend = RecordingPyAutoGUI()
    monkeypatch.setattr(shortcut_controller, "pyautogui", backend)
    controller = ShortcutController()
    controller.set_enabled(True)

    controller.execute(ShortcutAction.SWIPE_LEFT)
    controller.execute(ShortcutAction.SWIPE_RIGHT)

    assert backend.presses == ["left"] * 4 + ["right"] * 4


def test_vertical_swipes_scroll(monkeypatch) -> None:
    backend = RecordingPyAutoGUI()
    monkeypatch.setattr(shortcut_controller, "pyautogui", backend)
    controller = ShortcutController()
    controller.set_enabled(True)

    controller.execute(ShortcutAction.SWIPE_UP)
    controller.execute(ShortcutAction.SWIPE_DOWN)

    assert backend.scrolls == [20, -20]
