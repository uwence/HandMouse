import queue
import threading
import tkinter as tk
from tkinter import messagebox

_gui_lock = threading.Lock()
_gui_queue = queue.Queue()
_gui_thread_started = False
_gui_window = None

def _start_gui_thread_if_needed():
    global _gui_thread_started
    with _gui_lock:
        if not _gui_thread_started:
            threading.Thread(target=_gui_thread_worker, daemon=True).start()
            _gui_thread_started = True

def open_settings_in_thread(mode: str = "advanced") -> None:
    """Request the settings GUI to open via the persistent background thread."""
    _start_gui_thread_if_needed()
    if mode == "basic":
        _gui_queue.put("SHOW_BASIC_SETTINGS")
    else:
        _gui_queue.put("SHOW_ADVANCED_SETTINGS")

def open_calibration_wizard_in_thread() -> None:
    """Request the calibration wizard GUI to open via the persistent background thread."""
    _start_gui_thread_if_needed()
    _gui_queue.put("SHOW_CALIBRATION_WIZARD")

def open_about_in_thread() -> None:
    """Request the about dialog to open via the persistent background thread."""
    _start_gui_thread_if_needed()
    _gui_queue.put("SHOW_ABOUT")

def _gui_thread_worker():
    root = tk.Tk()
    root.withdraw() # Hide the root window initially
    
    def check_queue():
        try:
            while True:
                msg = _gui_queue.get_nowait()
                if msg == "SHOW_ADVANCED_SETTINGS":
                    from handmouse.ui.advanced_gui import _build_settings_ui
                    _build_settings_ui(root)
                elif msg == "SHOW_BASIC_SETTINGS":
                    from handmouse.ui.basic_gui import _build_basic_ui
                    _build_basic_ui(root)
                elif msg == "SHOW_CALIBRATION_WIZARD":
                    from handmouse.ui.calibration_wizard import _build_wizard_ui
                    _build_wizard_ui(root)
                elif msg == "SHOW_ABOUT":
                    _build_about_ui(root)
        except queue.Empty:
            pass
        root.after(100, check_queue)
        
    root.after(100, check_queue)
    root.mainloop()

def _build_about_ui(root):
    messagebox.showinfo(
        "About HandMouse",
        "HandMouse V3\n\n"
        "Windows hand gesture controller using webcam & MediaPipe.\n"
        "Status: Active (Green) / Idle (Gray)\n\n"
        "Developed as a premium desktop utility.",
        parent=root
    )
