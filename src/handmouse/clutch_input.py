from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from types import SimpleNamespace
from typing import Any

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105


@dataclass(frozen=True)
class ClutchSnapshot:
    clutch_down: bool


class ManualClutchInput:
    def __init__(self) -> None:
        self._pressed = False

    def set_pressed(self, pressed: bool) -> None:
        self._pressed = pressed

    def snapshot(self) -> ClutchSnapshot:
        return ClutchSnapshot(clutch_down=self._pressed)


class GlobalClutchInput:
    def __init__(self, key_name: str = "ctrl_r") -> None:
        self._pressed = False
        self._lock = Lock()
        self._listener: Any | None = None
        self._key_name = key_name

    def start(self) -> None:
        try:
            from pynput import keyboard
        except ImportError as exc:
            raise RuntimeError(
                "pynput is required for global clutch input. Install pynput."
            ) from exc

        try:
            target_key = getattr(keyboard.Key, self._key_name)
        except AttributeError as exc:
            raise RuntimeError(
                f"Unsupported clutch key: {self._key_name}"
            ) from exc
        accepted_keys = _accepted_keys(keyboard, self._key_name)
        target_vk = target_key.value.vk

        def on_press(key: Any) -> None:
            if _matches_clutch_key(key, accepted_keys, target_vk):
                with self._lock:
                    self._pressed = True

        def on_release(key: Any) -> None:
            if _matches_clutch_key(key, accepted_keys, target_vk):
                with self._lock:
                    self._pressed = False

        listener_ref: SimpleNamespace = SimpleNamespace(listener=None)

        def win32_event_filter(msg: Any, data: Any) -> bool:
            listener = listener_ref.listener
            vk_code = getattr(data, "vkCode", None)
            if vk_code == target_vk:
                if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    with self._lock:
                        self._pressed = True
                elif msg in (WM_KEYUP, WM_SYSKEYUP):
                    with self._lock:
                        self._pressed = False
            if (
                listener is not None
                and data is not None
                and vk_code == target_vk
            ):
                listener.suppress_event()
            return True

        self._listener = keyboard.Listener(
            on_press=on_press,
            on_release=on_release,
            win32_event_filter=win32_event_filter,
        )
        listener_ref.listener = self._listener
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def snapshot(self) -> ClutchSnapshot:
        with self._lock:
            return ClutchSnapshot(clutch_down=self._pressed)


def _accepted_keys(keyboard: Any, key_name: str) -> tuple[Any, ...]:
    alias_map = {
        "ctrl_r": ("ctrl_r", "ctrl"),
        "ctrl_l": ("ctrl_l", "ctrl"),
    }
    names = alias_map.get(key_name, (key_name,))
    return tuple(
        getattr(keyboard.Key, name)
        for name in names
        if hasattr(keyboard.Key, name)
    )


def _matches_clutch_key(key: Any, accepted_keys: tuple[Any, ...], target_vk: int) -> bool:
    if key in accepted_keys:
        return True

    key_vk = _extract_vk(key)
    return key_vk == target_vk


def _extract_vk(key: Any) -> int | None:
    if key is None:
        return None

    value = getattr(key, "value", key)
    vk = getattr(value, "vk", None)
    if vk is not None:
        return int(vk)

    return None


__all__ = [
    "ClutchSnapshot",
    "GlobalClutchInput",
    "ManualClutchInput",
]
