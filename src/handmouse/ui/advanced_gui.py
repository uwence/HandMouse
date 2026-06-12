from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

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
    dict_to_app_config,
    dataclass_to_dict,
    ViewConfig,
)

_gui_window = None

def _build_settings_ui(root) -> None:
    global _gui_window
    
    if _gui_window is not None and _gui_window.winfo_exists():
        _gui_window.lift()
        _gui_window.focus_force()
        return

    top = tk.Toplevel(root)
    _gui_window = top

    top.title("HandMouse Settings")
    top.geometry("450x820")
    top.resizable(False, False)

    # Configure dark theme colors
    bg_color = "#1e1e2e"       # Catppuccin Mocha base
    card_color = "#252538"     # Catppuccin Mocha surface
    text_color = "#cdd6f4"     # White/gray
    accent_color = "#89b4fa"   # Cyan/blue
    entry_bg = "#313244"       # Input background
    button_hover = "#b4befe"   # Purple/light blue

    top.configure(bg=bg_color)

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
    
    content = tk.Frame(top, bg=bg_color)
    content.pack(fill="both", expand=True)

    canvas = tk.Canvas(content, bg=bg_color, highlightthickness=0, bd=0)
    scrollbar = ttk.Scrollbar(content, orient="vertical", command=canvas.yview)
    scroll_inner = tk.Frame(canvas, bg=bg_color)

    scroll_window = canvas.create_window((0, 0), window=scroll_inner, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _sync_scroll_region(_: tk.Event | None = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _resize_inner(event: tk.Event) -> None:
        canvas.itemconfigure(scroll_window, width=event.width)

    def _on_mousewheel(event: tk.Event) -> None:
        delta = getattr(event, "delta", 0)
        if delta:
            canvas.yview_scroll(int(-delta / 120), "units")

    def _bind_mousewheel(_: tk.Event | None = None) -> None:
        top.bind_all("<MouseWheel>", _on_mousewheel)

    def _unbind_mousewheel(_: tk.Event | None = None) -> None:
        top.unbind_all("<MouseWheel>")

    scroll_inner.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _resize_inner)
    canvas.bind("<Enter>", _bind_mousewheel)
    canvas.bind("<Leave>", _unbind_mousewheel)
    scroll_inner.bind("<Enter>", _bind_mousewheel)
    scroll_inner.bind("<Leave>", _unbind_mousewheel)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # Custom Frame class for styled card containers
    def create_card(parent, title):
        frame = tk.Frame(parent, bg=card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        frame.pack(fill="x", padx=15, pady=8, ipady=5)
        
        title_lbl = tk.Label(frame, text=title, bg=card_color, fg=accent_color, font=section_font)
        title_lbl.pack(anchor="w", padx=10, pady=(5, 10))
        return frame

    # Title Banner
    banner = tk.Canvas(scroll_inner, height=60, bg=card_color, highlightthickness=0)
    banner.pack(fill="x", pady=(0, 10))
    # Draw a gradient-like bar or clean accent line
    banner.create_rectangle(0, 56, 450, 60, fill=accent_color, outline="")
    banner.create_text(225, 30, text="HANDMOUSE SETTINGS", fill=text_color, font=title_font)

    # Load current config
    import handmouse.config as conf
    config = conf.ACTIVE_CONFIG

    # Variables (MUST use master=top)
    camera_idx_var = tk.StringVar(master=top, value=str(config.camera.index))
    input_is_mirrored_var = tk.BooleanVar(master=top, value=config.camera.input_is_mirrored)
    render_mirrored_var = tk.BooleanVar(master=top, value=config.view.render_mirrored)
    speed_var = tk.DoubleVar(master=top, value=config.pointer.g_hi)
    pinch_close_var = tk.DoubleVar(master=top, value=config.gesture_config.pinch_close_ratio)
    pinch_open_var = tk.DoubleVar(master=top, value=config.gesture_config.pinch_open_ratio)
    scroll_sens_var = tk.DoubleVar(master=top, value=config.grab_scroll_config.scroll_sensitivity)

    switches = config.gesture_switches
    rc_var = tk.BooleanVar(master=top, value=switches.right_click)
    dc_var = tk.BooleanVar(master=top, value=switches.double_click)
    dd_var = tk.BooleanVar(master=top, value=switches.drag_drop)
    at_var = tk.BooleanVar(master=top, value=switches.alt_tab)
    wd_var = tk.BooleanVar(master=top, value=switches.win_d)
    osd_var = tk.BooleanVar(master=top, value=config.show_osd)

    # 1. Camera & Pointer Card
    card1 = create_card(scroll_inner, "Camera & Speed Configuration")
    
    row1 = tk.Frame(card1, bg=card_color)
    row1.pack(fill="x", padx=10, pady=5)
    tk.Label(row1, text="Webcam Device ID:", bg=card_color, fg=text_color).pack(side="left")
    camera_combo = ttk.Combobox(row1, textvariable=camera_idx_var, values=["0", "1", "2", "3", "4", "5"], width=5, state="readonly")
    camera_combo.pack(side="right")

    row2 = tk.Frame(card1, bg=card_color)
    row2.pack(fill="x", padx=10, pady=5)
    
    ttk.Checkbutton(row2, text="Hardware Camera is Mirrored", variable=input_is_mirrored_var).pack(side="left")

    row3 = tk.Frame(card1, bg=card_color)
    row3.pack(fill="x", padx=10, pady=5)
    
    ttk.Checkbutton(row3, text="Mirror Display (Render)", variable=render_mirrored_var).pack(side="left")

    row2_speed = tk.Frame(card1, bg=card_color)
    row2_speed.pack(fill="x", padx=10, pady=5)
    tk.Label(row2_speed, text="Pointer Speed (Gain):", bg=card_color, fg=text_color).pack(side="left")
    speed_lbl = tk.Label(row2_speed, text=f"{speed_var.get():.1f}x", bg=card_color, fg=accent_color, width=5)
    speed_lbl.pack(side="right")
    
    def _update_speed_lbl(val):
        speed_lbl.config(text=f"{float(val):.1f}x")
        
    speed_scale = tk.Scale(
        row2_speed, from_=1.0, to=10.0, resolution=0.5, orient="horizontal",
        variable=speed_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_speed_lbl
    )
    speed_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    # 2. Gesture Switches Card
    card2 = create_card(scroll_inner, "Enable / Disable Features")
    
    grid = tk.Frame(card2, bg=card_color)
    grid.pack(fill="x", padx=10, pady=5)

    ttk.Checkbutton(grid, text="Right Click (Thumb + Middle)", variable=rc_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Double Click (Double Pinch)", variable=dc_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Drag & Drop (Pinch + Move)", variable=dd_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Win+Tab Task View (3 Fingers)", variable=at_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Win+D Back to Desktop (Palm Swipe L/R)", variable=wd_var).pack(anchor="w", pady=3)
    ttk.Checkbutton(grid, text="Show On-Screen Display (OSD) feedback", variable=osd_var).pack(anchor="w", pady=3)

    # 3. Gesture Sensitivity Card
    card3 = create_card(scroll_inner, "Gesture Sensitivity")

    row3 = tk.Frame(card3, bg=card_color)
    row3.pack(fill="x", padx=10, pady=5)
    tk.Label(row3, text="Pinch Close Ratio:", bg=card_color, fg=text_color).pack(side="left")
    pinch_close_lbl = tk.Label(row3, text=f"{pinch_close_var.get():.3f}", bg=card_color, fg=accent_color, width=6)
    pinch_close_lbl.pack(side="right")
    
    def _update_close_lbl(val):
        pinch_close_lbl.config(text=f"{float(val):.3f}")
        
    pinch_close_scale = tk.Scale(
        row3, from_=0.2, to=0.8, resolution=0.01, orient="horizontal",
        variable=pinch_close_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_close_lbl
    )
    pinch_close_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    row4 = tk.Frame(card3, bg=card_color)
    row4.pack(fill="x", padx=10, pady=5)
    tk.Label(row4, text="Pinch Open Ratio:", bg=card_color, fg=text_color).pack(side="left")
    pinch_open_lbl = tk.Label(row4, text=f"{pinch_open_var.get():.3f}", bg=card_color, fg=accent_color, width=6)
    pinch_open_lbl.pack(side="right")
    
    def _update_open_lbl(val):
        pinch_open_lbl.config(text=f"{float(val):.3f}")
        
    pinch_open_scale = tk.Scale(
        row4, from_=0.3, to=1.2, resolution=0.01, orient="horizontal",
        variable=pinch_open_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_open_lbl
    )
    pinch_open_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    row5 = tk.Frame(card3, bg=card_color)
    row5.pack(fill="x", padx=10, pady=5)
    tk.Label(row5, text="Scroll Sensitivity:", bg=card_color, fg=text_color).pack(side="left")
    scroll_sens_lbl = tk.Label(row5, text=f"{scroll_sens_var.get():.0f}", bg=card_color, fg=accent_color, width=6)
    scroll_sens_lbl.pack(side="right")
    
    def _update_scroll_lbl(val):
        scroll_sens_lbl.config(text=f"{float(val):.0f}")
        
    scroll_sens_scale = tk.Scale(
        row5, from_=50.0, to=3000.0, resolution=50.0, orient="horizontal",
        variable=scroll_sens_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=False,
        command=_update_scroll_lbl
    )
    scroll_sens_scale.pack(side="right", fill="x", expand=True, padx=(10, 5))

    # Preset management callbacks
    def on_import_preset():
        file_path = filedialog.askopenfilename(
            parent=top,
            title="Import Profile Preset",
            filetypes=[("YAML Files", "*.yaml"), ("All Files", "*.*")]
        )
        if not file_path:
            return
        
        try:
            import yaml
            with open(file_path, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f)
            if not isinstance(d, dict):
                raise ValueError("Preset file is not a valid YAML dictionary.")
            
            imported_config = dict_to_app_config(d)
            
            # Update all tkinter variables with imported config values
            camera_idx_var.set(str(imported_config.camera.index))
            input_is_mirrored_var.set(imported_config.camera.input_is_mirrored)
            render_mirrored_var.set(imported_config.view.render_mirrored)
            speed_var.set(imported_config.pointer.g_hi)
            speed_lbl.config(text=f"{imported_config.pointer.g_hi:.1f}x")
            
            sw = imported_config.gesture_switches
            rc_var.set(sw.right_click)
            dc_var.set(sw.double_click)
            dd_var.set(sw.drag_drop)
            at_var.set(sw.alt_tab)
            wd_var.set(sw.win_d)
            osd_var.set(imported_config.show_osd)
            
            pinch_close_var.set(imported_config.gesture_config.pinch_close_ratio)
            pinch_close_lbl.config(text=f"{imported_config.gesture_config.pinch_close_ratio:.3f}")
            pinch_open_var.set(imported_config.gesture_config.pinch_open_ratio)
            pinch_open_lbl.config(text=f"{imported_config.gesture_config.pinch_open_ratio:.3f}")
            scroll_sens_var.set(imported_config.grab_scroll_config.scroll_sensitivity)
            scroll_sens_lbl.config(text=f"{imported_config.grab_scroll_config.scroll_sensitivity:.0f}")
            
            messagebox.showinfo("Import Success", "Preset imported successfully! Click 'Save & Apply' to finalize.", parent=top)
        except Exception as exc:
            messagebox.showerror("Import Error", f"Failed to import preset: {exc}", parent=top)

    def on_export_preset():
        file_path = filedialog.asksaveasfilename(
            parent=top,
            title="Export Profile Preset",
            defaultextension=".yaml",
            filetypes=[("YAML Files", "*.yaml"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            current_config = AppConfig(
                camera=CameraConfig(
                    width=config.camera.width,
                    height=config.camera.height,
                    index=int(camera_idx_var.get()),
                    backend_preference=config.camera.backend_preference,
                    fps_target=config.camera.fps_target,
                    buffer_size=config.camera.buffer_size,
                    input_is_mirrored=input_is_mirrored_var.get(),
                ),
                view=ViewConfig(
                    render_mirrored=render_mirrored_var.get(),
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
                    pinch_close_ratio=pinch_close_var.get(),
                    pinch_open_ratio=pinch_open_var.get(),
                ),
                grab_scroll_config=ExtendedGrabScrollConfig(
                    scroll_sensitivity=scroll_sens_var.get(),
                ),
                show_osd=osd_var.get(),
            )
            
            import yaml
            with open(file_path, "w", encoding="utf-8") as f:
                yaml.dump(dataclass_to_dict(current_config), f, default_flow_style=False, sort_keys=False)
                
            messagebox.showinfo("Export Success", "Preset exported successfully!", parent=top)
        except Exception as exc:
            messagebox.showerror("Export Error", f"Failed to export preset: {exc}", parent=top)

    # 4. Profile Preset Card
    card4 = create_card(scroll_inner, "Preset Profile Management")
    row_presets = tk.Frame(card4, bg=card_color)
    row_presets.pack(fill="x", padx=10, pady=5)
    
    import_btn = tk.Button(
        row_presets, text="Import Preset...", font=button_font, bg="#45475a", fg=text_color,
        activebackground="#585b70", activeforeground=text_color, bd=0, relief="flat",
        padx=12, pady=5, command=on_import_preset, cursor="hand2"
    )
    import_btn.pack(side="left", padx=(5, 10))
    
    export_btn = tk.Button(
        row_presets, text="Export Preset...", font=button_font, bg="#45475a", fg=text_color,
        activebackground="#585b70", activeforeground=text_color, bd=0, relief="flat",
        padx=12, pady=5, command=on_export_preset, cursor="hand2"
    )
    export_btn.pack(side="left")

    # Action Buttons
    btn_frame = tk.Frame(top, bg=bg_color)
    btn_frame.pack(side="bottom", fill="x", padx=15, pady=15)

    def on_save():
        # Validate pinch thresholds
        if pinch_close_var.get() >= pinch_open_var.get():
            messagebox.showerror(
                "Validation Error",
                "Pinch Close threshold must be strictly less than Pinch Open threshold."
            )
            return

        new_config = conf.AppConfig(
            camera=conf.CameraConfig(
                width=config.camera.width,
                height=config.camera.height,
                index=int(camera_idx_var.get()),
                backend_preference=config.camera.backend_preference,
                fps_target=config.camera.fps_target,
                buffer_size=config.camera.buffer_size,
                input_is_mirrored=input_is_mirrored_var.get(),
            ),
            view=conf.ViewConfig(
                render_mirrored=render_mirrored_var.get(),
            ),
            pointer=conf.PointerConfig(
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
                pinch_close_ratio=pinch_close_var.get(),
                pinch_open_ratio=pinch_open_var.get(),
            ),
            grab_scroll_config=ExtendedGrabScrollConfig(
                scroll_sensitivity=scroll_sens_var.get(),
            ),
            show_osd=osd_var.get(),
        )
        
        # Save to file
        save_config(new_config)
        
        # Update running config
        conf.ACTIVE_CONFIG = new_config
        
        messagebox.showinfo("Success", "Configuration saved and applied successfully!", parent=top)

    def on_cancel():
        top.destroy()
        global _gui_window
        _gui_window = None

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
        global _gui_window
        _gui_window = None
        _unbind_mousewheel()
        top.destroy()

    top.protocol("WM_DELETE_WINDOW", _cleanup)
