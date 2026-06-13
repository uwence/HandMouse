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
    import handmouse.ui.advanced_gui as advanced_gui
    import handmouse.ui.basic_gui as basic_gui
    import handmouse.ui.manager as manager
    advanced_gui._gui_window = None
    basic_gui._gui_window = None
    manager._gui_window = None
    yield
    advanced_gui._gui_window = None
    basic_gui._gui_window = None
    manager._gui_window = None


@pytest.fixture(autouse=True)
def _reset_app_globals() -> None:
    """Tray menu callbacks flip the ``handmouse.app`` module globals
    ``SHOULD_EXIT`` / ``PENDING_STATE_TOGGLE``. Reset them around every test so a
    tray test can't make a later ``_run_loop`` exit early under random ordering."""
    import handmouse.app as app
    app.SHOULD_EXIT = False
    app.PENDING_STATE_TOGGLE = False
    yield
    app.SHOULD_EXIT = False
    app.PENDING_STATE_TOGGLE = False


@pytest.fixture(autouse=True)
def _restore_active_config() -> None:
    """Calibration/GUI save flows reassign the module-global
    ``handmouse.config.ACTIVE_CONFIG``. Snapshot and restore it around every
    test so a saved config (e.g. with different gesture/bimanual fields) can't
    leak into unrelated tests under random ordering."""
    import handmouse.config as conf
    saved = conf.ACTIVE_CONFIG
    yield
    conf.ACTIVE_CONFIG = saved
