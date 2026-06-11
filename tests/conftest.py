"""Project-level pytest fixtures.

The GUI module (handmouse.gui) keeps a module-global `_gui_window` that
short-circuits `_build_settings_ui` when set. Without resetting it between
tests, a stale `MockTk` from a prior test can satisfy `winfo_exists()` and
silently skip settings construction.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_gui_window() -> None:
    from handmouse import gui as gui_module
    gui_module._gui_window = None
    yield
    gui_module._gui_window = None
