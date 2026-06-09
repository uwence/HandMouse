from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageDraw
import pystray

from handmouse.gui import open_settings_in_thread

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

        def on_settings(icon, item):
            open_settings_in_thread()

        def on_about(icon, item):
            def _msg():
                root = tk.Tk()
                root.withdraw()
                messagebox.showinfo(
                    "About HandMouse",
                    "HandMouse V3\n\n"
                    "Windows hand gesture controller using webcam & MediaPipe.\n"
                    "Status: Active (Green) / Idle (Gray)\n\n"
                    "Developed as a premium desktop utility."
                )
                root.destroy()
            threading.Thread(target=_msg, daemon=True).start()

        def on_exit(icon, item):
            from handmouse import app
            app.SHOULD_EXIT = True
            icon.stop()

        def run_tray():
            global _icon
            initial_image = _create_circle_icon("#6c7086")
            icon = pystray.Icon(
                "handmouse",
                icon=initial_image,
                title="HandMouse",
                menu=pystray.Menu(
                    pystray.MenuItem("Toggle Active/Idle", on_toggle),
                    pystray.MenuItem("Settings", on_settings),
                    pystray.MenuItem("About", on_about),
                    pystray.MenuItem("Exit", on_exit),
                )
            )
            with _tray_lock:
                _icon = icon
            icon.run()

        # Start in a background thread to prevent blocking main thread / OpenCV
        t = threading.Thread(target=run_tray, daemon=True)

    t.start()


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
