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
    """Tests must not depend on the developer's real ~/.handmouse/config.yaml,
    which is loaded into the module-global ``ACTIVE_CONFIG`` at import time and
    may have bimanual enabled, custom gesture switches, etc. (e.g. when the dev
    is dogfooding bimanual mode, every legacy single-hand test would take the
    bimanual branch and fail). Force a clean DEFAULT_CONFIG for every test and
    restore the loaded global afterward. Tests that need a specific config
    monkeypatch ACTIVE_CONFIG themselves; this also undoes any leak from
    calibration/GUI save flows that reassign the global."""
    import handmouse.config as conf
    saved = conf.ACTIVE_CONFIG
    conf.ACTIVE_CONFIG = conf.DEFAULT_CONFIG
    yield
    conf.ACTIVE_CONFIG = saved


@pytest.fixture(autouse=True)
def _redirect_config_path(tmp_path, monkeypatch) -> None:
    """``save_config``/``load_or_create_config`` fall back to the real user
    config at ``~/.handmouse/config.yaml`` when called with no path. The
    calibration wizard (``_apply_and_save``) and the settings GUI both save
    with no path argument, so running the suite would OVERWRITE the developer's
    real config. Both call the same ``handmouse.config`` function objects, which
    read these module globals at call time, so redirecting them to a per-test
    tmp dir keeps every no-path save off the real file. (``_restore_active_config``
    only guards the in-memory global, not the on-disk file.)"""
    import handmouse.config as conf
    tmp_dir = tmp_path / ".handmouse"
    monkeypatch.setattr(conf, "CONFIG_DIR", str(tmp_dir))
    monkeypatch.setattr(conf, "CONFIG_PATH_YAML", str(tmp_dir / "config.yaml"))
    monkeypatch.setattr(conf, "CONFIG_PATH_JSON", str(tmp_dir / "config.json"))
