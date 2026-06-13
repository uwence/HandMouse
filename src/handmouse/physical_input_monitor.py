from __future__ import annotations

import time
from threading import Lock
from typing import Any

# Low-level hook "injected" flags (winuser.h). Events synthesised by SendInput /
# mouse_event / keybd_event (i.e. HandMouse's own pyautogui + ctypes output) carry
# these flags, so we can tell the user's real input apart from our own.
LLKHF_INJECTED = 0x00000010  # KBDLLHOOKSTRUCT.flags
LLMHF_INJECTED = 0x00000001  # MSLLHOOKSTRUCT.flags


def _is_injected(flags: Any, mask: int) -> bool:
    """True when a low-level hook event was synthesised (not from real hardware)."""
    try:
        return bool(int(flags) & mask)
    except (TypeError, ValueError):
        return False


class PhysicalInputMonitor:
    """Tracks the last time the user produced *physical* (non-injected) mouse
    input, so the app can stand down gesture control while the user is
    driving the machine manually (e.g. a hand resting on the mouse is in the
    webcam's view and would otherwise be tracked as gestures that fight the real
    cursor).

    Uses Windows low-level hooks via pynput and the INJECTED flag to ignore
    HandMouse's own synthetic events — otherwise HandMouse moving the cursor would
    look like "physical input" and suspend itself in a feedback loop.
    Keyboard monitoring is opt-in because HandMouse's own physical control keys
    (activation and clutch) must not suspend gesture control.

    Degrades to a no-op (never reports recent physical input) when pynput or its
    win32 backend is unavailable, so non-Windows / headless runs are unaffected.
    """

    def __init__(self, *, monitor_mouse: bool = True, monitor_keyboard: bool = False) -> None:
        self._last_ms: int | None = None
        self._lock = Lock()
        self._monitor_mouse = monitor_mouse
        self._monitor_keyboard = monitor_keyboard
        self._kbd_listener: Any | None = None
        self._mouse_listener: Any | None = None

    def start(self) -> None:
        from pynput import keyboard, mouse

        def kbd_filter(msg: Any, data: Any) -> bool:
            return self._handle_keyboard_event(msg, data)

        def mouse_filter(msg: Any, data: Any) -> bool:
            return self._handle_mouse_event(msg, data)

        if self._monitor_keyboard:
            self._kbd_listener = keyboard.Listener(win32_event_filter=kbd_filter)
            self._kbd_listener.daemon = True
            self._kbd_listener.start()
        if self._monitor_mouse:
            self._mouse_listener = mouse.Listener(win32_event_filter=mouse_filter)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()

    def stop(self) -> None:
        for listener in (self._kbd_listener, self._mouse_listener):
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
        self._kbd_listener = None
        self._mouse_listener = None

    def _handle_keyboard_event(self, msg: Any, data: Any) -> bool:
        if self._monitor_keyboard and not _is_injected(getattr(data, "flags", 0), LLKHF_INJECTED):
            self._mark()
        return True

    def _handle_mouse_event(self, msg: Any, data: Any) -> bool:
        if self._monitor_mouse and not _is_injected(getattr(data, "flags", 0), LLMHF_INJECTED):
            self._mark()
        return True

    def _mark(self) -> None:
        ms = int(time.perf_counter() * 1000)
        with self._lock:
            self._last_ms = ms

    @property
    def last_physical_input_ms(self) -> int | None:
        with self._lock:
            return self._last_ms

    def is_recent(self, now_ms: int, grace_ms: int) -> bool:
        """True if physical input happened within the last ``grace_ms``.

        ``now_ms`` must come from the same ``time.perf_counter()`` clock the run
        loop uses. A diff below ``grace_ms`` (including a small negative diff from
        a mark that lands just after ``now_ms`` was captured) counts as recent.
        """
        with self._lock:
            last = self._last_ms
        return last is not None and (now_ms - last) < grace_ms


__all__ = ["PhysicalInputMonitor", "LLKHF_INJECTED", "LLMHF_INJECTED"]
