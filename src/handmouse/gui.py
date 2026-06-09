from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from handmouse import app
from handmouse.config import (
    AppConfig,
    CameraConfig,
    ClutchConfig,
    ControlRegion,
    ExtendedGestureConfig,
    ExtendedGrabScrollConfig,
    GestureSwitches,
    PointerConfig,
    ShortcutConfig,
    save_config,
)

_gui_lock = threading.Lock()
_gui_window = None


def open_settings_in_thread() -> None:
    """Open the settings GUI in a separate thread to avoid blocking the main loop."""
    with _gui_lock:
        global _gui_window
        if _gui_window is not None:
            try:
                _gui_window.lift()
                _gui_window.focus_force()
                return
            except Exception:
                _gui_window = None

        t = threading.Thread(target=_run_gui, daemon=True)
        t.start()


def _run_gui() -> None:
    global _gui_window
    
    root = tk.Tk()
    with _gui_lock:
        _gui_window = root

    root.title("HandMouse Settings")
    root.geometry("450x660")
    root.resizable(False, False)

    # Configure dark theme colors
    bg_color = "#1e1e2e"       # Catppuccin Mocha base
    card_color = "#252538"     # Catppuccin Mocha surface
    text_color = "#cdd6f4"     # White/gray
    accent_color = "#89b4fa"   # Cyan/blue
    entry_bg = "#313244"       # Input background
    button_hover = "#b4befe"   # Purple/light blue

    root.configure(bg=bg_color)

    # Fonts
    font_family = "Segoe UI"
    title_font = (font_family, 16, "bold")
    section_font = (font_family, 11, "bold")
    label_font = (font_family, 10)
    button_font = (font_family, 10, "bold")

    # Tkinter ttk styles
    style = ttk.Style()
    style.theme_use("clam")
    style.configure(".", background=bg_color, foreground=text_color)
    style.configure("TFrame", background=bg_color)
    style.configure("TLabel", background=bg_color, foreground=text_color, font=label_font)
    style.configure("TCheckbutton", background=bg_color, foreground=text_color, font=label_font)
    style.map("TCheckbutton", background=[("active", bg_color)], foreground=[("active", accent_color)])
    style.configure("TCombobox", fieldbackground=entry_bg, background=card_color, foreground=text_color, font=label_font)
    
    # Custom Frame class for styled card containers
    def create_card(parent, title):
        frame = tk.Frame(parent, bg=card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        frame.pack(fill="x", padx=15, pady=8, ipady=5)
        
        title_lbl = tk.Label(frame, text=title, bg=card_color, fg=accent_color, font=section_font)
        title_lbl.pack(anchor="w", padx=10, pady=(5, 10))
        return frame

    # Title Banner
    banner = tk.Canvas(root, height=60, bg=card_color, highlightthickness=0)
    banner.pack(fill="x", pady=(0, 10))
    # Draw a gradient-like bar or clean accent line
    banner.create_rectangle(0, 56, 450, 60, fill=accent_color, outline="")
    banner.create_text(225, 30, text="HANDMOUSE SETTINGS", fill=text_color, font=title_font)

    # Load current config
    config = app.ACTIVE_CONFIG

    # Variables
    camera_idx_var = tk.StringVar(value=str(config.camera.index))
    speed_var = tk.DoubleVar(value=config.pointer.g_hi)
    pinch_close_var = tk.DoubleVar(value=config.gesture_config.pinch_close)
    pinch_open_var = tk.DoubleVar(value=config.gesture_config.pinch_open)
    scroll_sens_var = tk.DoubleVar(value=config.grab_scroll_config.scroll_sensitivity)

    switches = config.gesture_switches
    rc_var = tk.BooleanVar(value=switches.right_click)
    dc_var = tk.BooleanVar(value=switches.double_click)
    dd_var = tk.BooleanVar(value=switches.drag_drop)
    at_var = tk.BooleanVar(value=switches.alt_tab)
    wd_var = tk.BooleanVar(value=switches.win_d)

    # 1. Camera & Pointer Card
    card1 = create_card(root, "Camera & Speed Configuration")
    
    row1 = tk.Frame(card1, bg=card_color)
    row1.pack(fill="x", padx=10, pady=5)
    tk.Label(row1, text="Webcam Device ID:", bg=card_color, fg=text_color).pack(side="left")
    camera_combo = ttk.Combobox(row1, textvariable=camera_idx_var, values=["0", "1", "2", "3", "4", "5"], width=5, state="readonly")
    camera_combo.pack(side="right")

    row2 = tk.Frame(card1, bg=card_color)
    row2.pack(fill="x", padx=10, pady=8)
    tk.Label(row2, text="Pointer Max Speed:", bg=card_color, fg=text_color).pack(side="left")
    
    speed_lbl = tk.Label(row2, text=f"{speed_var.get():.1f}x", bg=card_color, fg=accent_color, width=5)
    speed_lbl.pack(side="right")
    
    def _update_speed_lbl(val):
        speed_lbl.config(text=f"{float(val):.1f}x")
        
    speed_scale = tk.Scale(
        row2, from_=1.0, to=10.0, resolution=0.5, orient="horizontal",
        variable=speed_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_speed_lbl
    )
    speed_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    # 2. Gesture Switches Card
    card2 = create_card(root, "Enable / Disable Gestures")
    
    grid = tk.Frame(card2, bg=card_color)
    grid.pack(fill="x", padx=10, pady=5)

    ttk.Checkbutton(grid, text="Right Click (Thumb + Middle)", variable=rc_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Double Click (Double Pinch)", variable=dc_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Drag & Drop (Pinch + Move)", variable=dd_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Alt+Tab Window Switcher (3 Fingers)", variable=at_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Win+D Back to Desktop (Palm Swipe)", variable=wd_var).pack(anchor="w", pady=3)

    # 3. Gesture Sensitivity Card
    card3 = create_card(root, "Gesture Sensitivity")

    row3 = tk.Frame(card3, bg=card_color)
    row3.pack(fill="x", padx=10, pady=5)
    tk.Label(row3, text="Pinch Close Threshold:", bg=card_color, fg=text_color).pack(side="left")
    pinch_close_lbl = tk.Label(row3, text=f"{pinch_close_var.get():.3f}", bg=card_color, fg=accent_color, width=6)
    pinch_close_lbl.pack(side="right")
    
    def _update_close_lbl(val):
        pinch_close_lbl.config(text=f"{float(val):.3f}")
        
    pinch_close_scale = tk.Scale(
        row3, from_=0.01, to=0.15, resolution=0.005, orient="horizontal",
        variable=pinch_close_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_close_lbl
    )
    pinch_close_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    row4 = tk.Frame(card3, bg=card_color)
    row4.pack(fill="x", padx=10, pady=5)
    tk.Label(row4, text="Pinch Open Threshold:", bg=card_color, fg=text_color).pack(side="left")
    pinch_open_lbl = tk.Label(row4, text=f"{pinch_open_var.get():.3f}", bg=card_color, fg=accent_color, width=6)
    pinch_open_lbl.pack(side="right")
    
    def _update_open_lbl(val):
        pinch_open_lbl.config(text=f"{float(val):.3f}")
        
    pinch_open_scale = tk.Scale(
        row4, from_=0.02, to=0.20, resolution=0.005, orient="horizontal",
        variable=pinch_open_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_open_lbl
    )
    pinch_open_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    row5 = tk.Frame(card3, bg=card_color)
    row5.pack(fill="x", padx=10, pady=5)
    tk.Label(row5, text="Scroll Sensitivity:", bg=card_color, fg=text_color).pack(side="left")
    scroll_sens_lbl = tk.Label(row5, text=f"{int(scroll_sens_var.get())}", bg=card_color, fg=accent_color, width=5)
    scroll_sens_lbl.pack(side="right")
    
    def _update_scroll_lbl(val):
        scroll_sens_lbl.config(text=f"{int(float(val))}")
        
    scroll_sens_scale = tk.Scale(
        row5, from_=50.0, to=500.0, resolution=10.0, orient="horizontal",
        variable=scroll_sens_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_scroll_lbl
    )
    scroll_sens_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    # Action Buttons
    btn_frame = tk.Frame(root, bg=bg_color)
    btn_frame.pack(fill="x", padx=15, pady=15)

    def on_save():
        # Validate pinch thresholds
        if pinch_close_var.get() >= pinch_open_var.get():
            messagebox.showerror(
                "Validation Error",
                "Pinch Close threshold must be strictly less than Pinch Open threshold."
            )
            return

        new_config = AppConfig(
            camera=CameraConfig(
                width=config.camera.width,
                height=config.camera.height,
                index=int(camera_idx_var.get()),
                backend_preference=config.camera.backend_preference,
                buffer_size=config.camera.buffer_size,
                fps_target=config.camera.fps_target,
            ),
            pointer=PointerConfig(
                control_region=config.pointer.control_region,
                g_hi=speed_var.get(),
            ),
            shortcut=config.shortcut,
            clutch=config.clutch,
            gesture_switches=GestureSwitches(
                right_click=rc_var.get(),
                double_click=dc_var.get(),
                drag_drop=dd_var.get(),
                alt_tab=at_var.get(),
                win_d=wd_var.get(),
            ),
            gesture_config=ExtendedGestureConfig(
                pinch_close=pinch_close_var.get(),
                pinch_open=pinch_open_var.get(),
            ),
            grab_scroll_config=ExtendedGrabScrollConfig(
                scroll_sensitivity=scroll_sens_var.get(),
            ),
        )
        
        # Save to file
        save_config(new_config)
        
        # Update running config
        app.ACTIVE_CONFIG = new_config
        
        messagebox.showinfo("Success", "Configuration saved and applied successfully!")
        root.destroy()

    def on_cancel():
        root.destroy()

    # Create beautiful custom action buttons
    # Since ttk buttons are hard to style with round corners, we use canvas or tk.Button with flat styling
    save_btn = tk.Button(
        btn_frame, text="Save & Apply", font=button_font, bg=accent_color, fg=bg_color,
        activebackground=button_hover, activeforeground=bg_color, bd=0, relief="flat",
        padx=15, pady=8, command=on_save, cursor="hand2"
    )
    save_btn.pack(side="right", padx=(10, 0))

    cancel_btn = tk.Button(
        btn_frame, text="Cancel", font=button_font, bg="#45475a", fg=text_color,
        activebackground="#585b70", activeforeground=text_color, bd=0, relief="flat",
        padx=15, pady=8, command=on_cancel, cursor="hand2"
    )
    cancel_btn.pack(side="right")

    def _cleanup():
        with _gui_lock:
            global _gui_window
            _gui_window = None
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _cleanup)
    root.mainloop()
