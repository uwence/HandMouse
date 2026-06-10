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
        self._drawn_text: str = ""
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

        self._canvas = tk.Canvas(self._root, bg="black", highlightthickness=0)
        self._canvas.pack(padx=20, pady=20)
        import tkinter.font as tkfont
        self._font = tkfont.Font(family="Segoe UI", size=32, weight="bold")
        
        self._root.after(50, self._animation_loop)
        self._root.mainloop()

    def _animation_loop(self):
        if not self._running:
            return
            
        with self._lock:
            now = time.time()
            time_since_update = now - self._last_update_time
            
            # The maximum opacity of the entire box (making it look like frosted glass)
            max_alpha = 0.85
            
            # Draw text if it has changed
            if hasattr(self, '_canvas'):
                if self._current_text != self._drawn_text:
                    self._draw_canvas(self._current_text)
                    self._drawn_text = self._current_text
            
            # Keep visible for 1.2 seconds, then fade out over 1.0 second
            if time_since_update < 1.2:
                self._opacity = max_alpha
            elif time_since_update < 2.2:
                progress = (time_since_update - 1.2) / 1.0
                self._opacity = max(0.0, max_alpha * (1.0 - progress))
            else:
                self._opacity = 0.0
                if hasattr(self, '_canvas') and self._drawn_text != "":
                    self._canvas.delete("all")
                    self._drawn_text = ""
                
        try:
            self._root.attributes("-alpha", self._opacity)
        except Exception:
            pass
            
        if self._running:
            self._root.after(30, self._animation_loop)

    def _draw_canvas(self, text: str):
        if not text:
            self._canvas.delete("all")
            return
            
        # Measure text to determine box size
        padding_x = 30
        padding_y = 15
        text_width = self._font.measure(text)
        text_height = self._font.metrics("linespace")
        
        box_width = text_width + padding_x * 2
        box_height = text_height + padding_y * 2
        
        # Resize canvas to exactly fit the box
        self._canvas.config(width=box_width, height=box_height)
        
        self._canvas.delete("all")
        
        # Draw rounded rectangle
        x1, y1 = 2, 2
        x2, y2 = box_width - 2, box_height - 2
        radius = 16
        points = [
            x1+radius, y1,
            x1+radius, y1,
            x2-radius, y1,
            x2-radius, y1,
            x2, y1,
            x2, y1+radius,
            x2, y1+radius,
            x2, y2-radius,
            x2, y2-radius,
            x2, y2,
            x2-radius, y2,
            x2-radius, y2,
            x1+radius, y2,
            x1+radius, y2,
            x1, y2,
            x1, y2-radius,
            x1, y2-radius,
            x1, y1+radius,
            x1, y1+radius,
            x1, y1
        ]
        
        self._canvas.create_polygon(
            points, 
            fill="#1A1A1A", 
            outline="#555555", 
            width=2, 
            smooth=True
        )
        
        # Draw text
        self._canvas.create_text(
            box_width / 2, box_height / 2,
            text=text,
            font=self._font,
            fill="white",
            anchor="center"
        )

    def show_text(self, text: str):
        if not self.enabled:
            return
            
        with self._lock:
            self._current_text = text
            self._last_update_time = time.time()
