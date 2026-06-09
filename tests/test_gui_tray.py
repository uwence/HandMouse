from __future__ import annotations

import sys
import tkinter as tk
from unittest.mock import MagicMock
import pytest

import handmouse.tray as tray_module
import handmouse.gui as gui_module
from handmouse.config import DEFAULT_CONFIG


class MockIcon:
    def __init__(self, name, icon, title, menu) -> None:
        self.name = name
        self.icon = icon
        self.title = title
        self.menu = menu
        self.run_called = False
        self.stop_called = False

    def run(self) -> None:
        self.run_called = True

    def stop(self) -> None:
        self.stop_called = True


def test_tray_icon_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_icon_instance = None

    def mock_icon_init(name, icon, title, menu):
        nonlocal mock_icon_instance
        mock_icon_instance = MockIcon(name, icon, title, menu)
        return mock_icon_instance

    monkeypatch.setattr("pystray.Icon", mock_icon_init)
    monkeypatch.setattr("pystray.Menu", lambda *args: list(args))
    monkeypatch.setattr("pystray.MenuItem", lambda text, action, **kwargs: (text, action))

    # Test start
    tray_module.start_tray_icon()
    assert mock_icon_instance is not None

    # Test status updates
    tray_module.update_tray_status(True)
    tray_module.update_tray_status(False)

    # Test menu callbacks
    menu_items = mock_icon_instance.menu
    # "Toggle Active/Idle" is first item
    toggle_callback = menu_items[0][1]
    toggle_callback(mock_icon_instance, None)
    
    # "Exit" is fourth item
    exit_callback = menu_items[3][1]
    exit_callback(mock_icon_instance, None)

    # Test stop
    tray_module.stop_tray_icon()
    assert mock_icon_instance.stop_called is True


def test_gui_run_and_save(monkeypatch: pytest.MonkeyPatch) -> None:
    # Capturing variables and commands
    save_callback = None
    cancel_callback = None

    class MockTk:
        def __init__(self) -> None:
            self.title_val = ""
            self.geometry_val = ""
            self.resizable_val = None
            self.protocol_funcs = {}

        def title(self, val) -> None:
            self.title_val = val

        def geometry(self, val) -> None:
            self.geometry_val = val

        def resizable(self, w, h) -> None:
            self.resizable_val = (w, h)

        def configure(self, **kwargs) -> None:
            pass

        def protocol(self, name, func) -> None:
            self.protocol_funcs[name] = func

        def mainloop(self) -> None:
            pass

        def destroy(self) -> None:
            pass

    class MockVar:
        def __init__(self, value=None) -> None:
            self._val = value
        def get(self):
            return self._val
        def set(self, val):
            self._val = val

    class MockButton:
        def __init__(self, parent, text, **kwargs) -> None:
            nonlocal save_callback, cancel_callback
            if "Save" in text:
                save_callback = kwargs.get("command")
            elif "Cancel" in text:
                cancel_callback = kwargs.get("command")

        def pack(self, **kwargs) -> None:
            pass

    # Mock tkinter classes & methods
    monkeypatch.setattr(tk, "Tk", MockTk)
    monkeypatch.setattr(tk, "StringVar", MockVar)
    monkeypatch.setattr(tk, "DoubleVar", MockVar)
    monkeypatch.setattr(tk, "BooleanVar", MockVar)
    monkeypatch.setattr(tk, "Frame", MagicMock())
    monkeypatch.setattr(tk, "Label", MagicMock())
    monkeypatch.setattr(tk, "Scale", MagicMock())
    monkeypatch.setattr(tk, "Canvas", MagicMock())
    monkeypatch.setattr(tk, "Button", MockButton)
    
    mock_style = MagicMock()
    monkeypatch.setattr("tkinter.ttk.Style", lambda: mock_style)
    
    mock_combobox = MagicMock()
    monkeypatch.setattr("tkinter.ttk.Combobox", lambda *args, **kwargs: mock_combobox)
    
    mock_checkbutton = MagicMock()
    monkeypatch.setattr("tkinter.ttk.Checkbutton", lambda *args, **kwargs: mock_checkbutton)

    mock_messagebox = MagicMock()
    monkeypatch.setattr("tkinter.messagebox.showinfo", mock_messagebox.showinfo)
    monkeypatch.setattr("tkinter.messagebox.showerror", mock_messagebox.showerror)

    # Trigger GUI run in the same thread for testing
    gui_module._run_gui()

    # Verify we captured the callbacks
    assert save_callback is not None
    assert cancel_callback is not None

    # Trigger save
    save_callback()

    # Trigger cancel
    cancel_callback()
