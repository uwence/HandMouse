from types import ModuleType, SimpleNamespace
import sys

from handmouse.clutch_input import ClutchSnapshot, ManualClutchInput
from handmouse.clutch_input import GlobalClutchInput


def test_manual_clutch_input_tracks_press_and_release() -> None:
    clutch = ManualClutchInput()

    clutch.set_pressed(True)
    first = clutch.snapshot()
    clutch.set_pressed(False)
    second = clutch.snapshot()

    assert first == ClutchSnapshot(clutch_down=True)
    assert second == ClutchSnapshot(clutch_down=False)


def test_global_clutch_input_updates_pressed_state(monkeypatch) -> None:
    listener_box: dict[str, object] = {}

    class FakeListener:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.daemon = False
            self.started = False
            listener_box["listener"] = self

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

        def suppress_event(self) -> None:
            listener_box["suppressed"] = True

    fake_keyboard = SimpleNamespace(
        Key=SimpleNamespace(ctrl_r=SimpleNamespace(value=SimpleNamespace(vk=163))),
        Listener=FakeListener,
    )
    fake_pynput = ModuleType("pynput")
    fake_pynput.keyboard = fake_keyboard
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)

    clutch = GlobalClutchInput("ctrl_r")
    clutch.start()

    listener = listener_box["listener"]
    listener.kwargs["on_press"](fake_keyboard.Key.ctrl_r)
    first = clutch.snapshot()
    listener.kwargs["on_release"](fake_keyboard.Key.ctrl_r)
    second = clutch.snapshot()

    assert first == ClutchSnapshot(clutch_down=True)
    assert second == ClutchSnapshot(clutch_down=False)
    assert listener.started is True


def test_global_clutch_input_suppresses_only_right_ctrl(monkeypatch) -> None:
    listener_box: dict[str, object] = {}

    class FakeListener:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.daemon = False
            self.suppressed = 0
            listener_box["listener"] = self

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def suppress_event(self) -> None:
            self.suppressed += 1

    fake_keyboard = SimpleNamespace(
        Key=SimpleNamespace(ctrl_r=SimpleNamespace(value=SimpleNamespace(vk=163))),
        Listener=FakeListener,
    )
    fake_pynput = ModuleType("pynput")
    fake_pynput.keyboard = fake_keyboard
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)

    clutch = GlobalClutchInput("ctrl_r")
    clutch.start()

    listener = listener_box["listener"]
    event_filter = listener.kwargs["win32_event_filter"]
    event_filter(0, SimpleNamespace(vkCode=163))
    event_filter(0, SimpleNamespace(vkCode=119))

    assert listener.suppressed == 1


def test_global_clutch_input_accepts_generic_ctrl_alias(monkeypatch) -> None:
    listener_box: dict[str, object] = {}

    class FakeListener:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.daemon = False
            listener_box["listener"] = self

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def suppress_event(self) -> None:
            pass

    fake_keyboard = SimpleNamespace(
        Key=SimpleNamespace(
            ctrl=SimpleNamespace(value=SimpleNamespace(vk=17)),
            ctrl_r=SimpleNamespace(value=SimpleNamespace(vk=163)),
        ),
        Listener=FakeListener,
    )
    fake_pynput = ModuleType("pynput")
    fake_pynput.keyboard = fake_keyboard
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)

    clutch = GlobalClutchInput("ctrl_r")
    clutch.start()

    listener = listener_box["listener"]
    listener.kwargs["on_press"](fake_keyboard.Key.ctrl)
    snapshot = clutch.snapshot()

    assert snapshot == ClutchSnapshot(clutch_down=True)


def test_global_clutch_input_tracks_press_and_release_from_win32_filter(monkeypatch) -> None:
    listener_box: dict[str, object] = {}

    class FakeListener:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs
            self.daemon = False
            listener_box["listener"] = self

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

        def suppress_event(self) -> None:
            pass

    fake_keyboard = SimpleNamespace(
        Key=SimpleNamespace(ctrl_r=SimpleNamespace(value=SimpleNamespace(vk=163))),
        Listener=FakeListener,
    )
    fake_pynput = ModuleType("pynput")
    fake_pynput.keyboard = fake_keyboard
    monkeypatch.setitem(sys.modules, "pynput", fake_pynput)

    clutch = GlobalClutchInput("ctrl_r")
    clutch.start()

    listener = listener_box["listener"]
    event_filter = listener.kwargs["win32_event_filter"]
    event_filter(0x0100, SimpleNamespace(vkCode=163))
    pressed = clutch.snapshot()
    event_filter(0x0101, SimpleNamespace(vkCode=163))
    released = clutch.snapshot()

    assert pressed == ClutchSnapshot(clutch_down=True)
    assert released == ClutchSnapshot(clutch_down=False)
