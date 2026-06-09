import threading
import time
import tkinter as tk
from typing import Optional

try:
    import win32gui
    import win32con
except ImportError:
    win32gui = None


class OSDManager:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._thread: Optional[threading.Thread] = None
        self._root: Optional[tk.Tk] = None
        self._label: Optional[tk.Label] = None
        self._text_var: Optional[tk.StringVar] = None
        self._current_text: str = ""
        self._last_update_time: float = 0
        self._opacity: float = 0.0
        self._running = False
        self._lock = threading.Lock()
        
        if self.enabled:
            self.start()

    def set_enabled(self, enabled: bool):
        if enabled and not self.enabled:
            self.enabled = True
            self.start()
        elif not enabled and self.enabled:
            self.enabled = False
            self.stop()

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_tk_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._root is not None:
            try:
                self._root.after(0, self._root.destroy)
            except Exception:
                pass
        self._thread = None

    def _run_tk_loop(self):
        self._root = tk.Tk()
        self._root.title("HandMouse OSD")
        self._root.overrideredirect(True) # Borderless
        self._root.attributes("-topmost", True)
        
        # Transparent background using a specific color key
        transparent_color = "black"
        self._root.configure(bg=transparent_color)
        self._root.wm_attributes("-transparentcolor", transparent_color)
        self._root.attributes("-alpha", 0.0) # Start invisible
        
        # Position top-left
        self._root.geometry("+50+50")
        
        self._root.update()
        if win32gui:
            try:
                hwnd = int(self._root.wm_frame(), 16)
                # Add WS_EX_LAYERED and WS_EX_TRANSPARENT
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
                win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, style | win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT)
            except Exception as e:
                print(f"Failed to set click-through on OSD: {e}")

        self._text_var = tk.StringVar()
        self._label = tk.Label(
            self._root,
            textvariable=self._text_var,
            font=("Segoe UI", 36, "bold"),
            fg="#00FFCC", # Cyan text
            bg=transparent_color,
            justify="left"
        )
        self._label.pack(padx=20, pady=20)
        
        self._root.after(50, self._animation_loop)
        self._root.mainloop()

    def _animation_loop(self):
        if not self._running:
            return
            
        with self._lock:
            now = time.time()
            time_since_update = now - self._last_update_time
            
            # Keep visible for 1.2 seconds, then fade out over 1.0 second
            if time_since_update < 1.2:
                self._opacity = 1.0
            elif time_since_update < 2.2:
                progress = (time_since_update - 1.2) / 1.0
                self._opacity = max(0.0, 1.0 - progress)
            else:
                self._opacity = 0.0
                if self._text_var is not None and self._text_var.get() != "":
                    self._text_var.set("") # Clear text to prevent artifacts
                
        try:
            self._root.attributes("-alpha", self._opacity)
        except Exception:
            pass
            
        if self._running:
            self._root.after(30, self._animation_loop)

    def show_text(self, text: str):
        if not self.enabled:
            return
            
        with self._lock:
            self._current_text = text
            self._last_update_time = time.time()
            if self._text_var is not None:
                self._text_var.set(text)
