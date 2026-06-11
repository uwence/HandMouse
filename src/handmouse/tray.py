from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray

from handmouse.ui.manager import open_settings_in_thread, open_about_in_thread

_tray_lock = threading.Lock()
_icon: pystray.Icon | None = None
_last_active_state: bool | None = None


def _create_circle_icon(color_hex: str) -> Image.Image:
    """Create a high-quality circle image of a specific color for the tray icon."""
    r = int(color_hex[1:3], 16)
    g = int(color_hex[3:5], 16)
    b = int(color_hex[5:7], 16)
    
    # 64x64 icon size
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    dc = ImageDraw.Draw(image)
    
    # Draw a smooth antialiased circle with simple padding and high-contrast white border
    dc.ellipse([4, 4, 60, 60], fill=(r, g, b, 255), outline=(255, 255, 255, 255), width=4)
    return image


def start_tray_icon() -> None:
    """Initialize and run the pystray system tray icon in a daemon background thread."""
    global _icon
    with _tray_lock:
        if _icon is not None:
            return

        def on_toggle(icon, item):
            from handmouse import app
            app.PENDING_STATE_TOGGLE = True

        def on_settings_basic(icon, item):
            open_settings_in_thread("basic")
            
        def on_settings_advanced(icon, item):
            open_settings_in_thread("advanced")

        def on_about_action(icon, item):
            open_about_in_thread()

        def on_exit(icon, item):
            from handmouse import app
            app.SHOULD_EXIT = True
            icon.stop()

        def set_profile(profile_name: str):
            def _inner(icon, item):
                from handmouse.config.profiles import get_profile
                from handmouse.config import save_config
                import handmouse.config as conf
                new_cfg = get_profile(profile_name)
                save_config(new_cfg)
                conf.ACTIVE_CONFIG = new_cfg
            return _inner

        initial_image = _create_circle_icon("#6c7086")
        icon = pystray.Icon(
            "handmouse",
            icon=initial_image,
            title="HandMouse",
            menu=pystray.Menu(
                pystray.MenuItem("Toggle Active/Idle", on_toggle),
                pystray.MenuItem("Profiles", pystray.Menu(
                    pystray.MenuItem("Default", set_profile("default")),
                    pystray.MenuItem("Aggressive", set_profile("aggressive")),
                    pystray.MenuItem("Conservative", set_profile("conservative")),
                )),
                pystray.MenuItem("Settings (Basic)", on_settings_basic),
                pystray.MenuItem("Settings (Advanced)", on_settings_advanced),
                pystray.MenuItem("About", on_about_action),
                pystray.MenuItem("Exit", on_exit),
            )
        )
        _icon = icon
        
        ready_event = threading.Event()
        def setup(icon_obj):
            ready_event.set()
            
        icon.run_detached(setup=setup)
        # Wait for the tray icon to actually start its message loop
        ready_event.wait(timeout=2.0)

def start_tray_icon_blocking() -> None:
    """Initialize and run the pystray system tray icon in the main thread (blocking)."""
    global _icon
    with _tray_lock:
        if _icon is not None:
            return

        def on_toggle(icon, item):
            from handmouse import app
            app.PENDING_STATE_TOGGLE = True

        def on_settings_basic(icon, item):
            open_settings_in_thread("basic")
            
        def on_settings_advanced(icon, item):
            open_settings_in_thread("advanced")

        def on_about_action(icon, item):
            open_about_in_thread()

        def on_exit(icon, item):
            from handmouse import app
            app.SHOULD_EXIT = True
            icon.stop()

        def set_profile(profile_name: str):
            def _inner(icon, item):
                from handmouse.config.profiles import get_profile
                from handmouse.config import save_config
                import handmouse.config as conf
                new_cfg = get_profile(profile_name)
                save_config(new_cfg)
                conf.ACTIVE_CONFIG = new_cfg
            return _inner

        initial_image = _create_circle_icon("#6c7086")
        icon = pystray.Icon(
            "handmouse",
            icon=initial_image,
            title="HandMouse",
            menu=pystray.Menu(
                pystray.MenuItem("Toggle Active/Idle", on_toggle),
                pystray.MenuItem("Profiles", pystray.Menu(
                    pystray.MenuItem("Default", set_profile("default")),
                    pystray.MenuItem("Aggressive", set_profile("aggressive")),
                    pystray.MenuItem("Conservative", set_profile("conservative")),
                )),
                pystray.MenuItem("Settings (Basic)", on_settings_basic),
                pystray.MenuItem("Settings (Advanced)", on_settings_advanced),
                pystray.MenuItem("About", on_about_action),
                pystray.MenuItem("Exit", on_exit),
            )
        )
        _icon = icon
    
    # Run blocking (must be outside lock so it doesn't deadlock on updates)
    icon.run()


def update_tray_status(is_active: bool) -> None:
    """Update the tray icon image color based on the ACTIVE/IDLE status."""
    global _icon, _last_active_state
    if is_active == _last_active_state:
        return

    with _tray_lock:
        if _icon is None:
            return
        
        _last_active_state = is_active
        # Active: Green, Idle: Gray
        color = "#a6e3a1" if is_active else "#6c7086"
        _icon.icon = _create_circle_icon(color)


def stop_tray_icon() -> None:
    """Cleanly stop the tray icon loop."""
    global _icon, _last_active_state
    with _tray_lock:
        if _icon is not None:
            _icon.stop()
            _icon = None
            _last_active_state = None
