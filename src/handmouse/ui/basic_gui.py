import tkinter as tk
from tkinter import ttk

_gui_window = None

def _build_basic_ui(root) -> None:
    global _gui_window
    
    if _gui_window is not None and _gui_window.winfo_exists():
        _gui_window.lift()
        _gui_window.focus_force()
        return

    top = tk.Toplevel(root)
    _gui_window = top

    top.title("HandMouse Basic Settings")
    top.geometry("400x400")
    top.resizable(False, False)

    bg_color = "#1e1e2e"
    card_color = "#252538"
    text_color = "#cdd6f4"
    accent_color = "#89b4fa"
    entry_bg = "#313244"
    button_hover = "#b4befe"

    root.configure(bg=bg_color)
    top.configure(bg=bg_color)

    font_family = "Segoe UI"
    title_font = (font_family, 14, "bold")
    label_font = (font_family, 10)

    banner = tk.Canvas(top, height=50, bg=card_color, highlightthickness=0)
    banner.pack(fill="x", pady=(0, 10))
    banner.create_rectangle(0, 46, 400, 50, fill=accent_color, outline="")
    banner.create_text(200, 25, text="BASIC SETTINGS", fill=text_color, font=title_font)

    import handmouse.config as conf
    from handmouse.config import save_config
    config = conf.ACTIVE_CONFIG

    camera_idx_var = tk.StringVar(master=top, value=str(config.camera.index))
    speed_var = tk.DoubleVar(master=top, value=config.pointer.g_hi)
    osd_var = tk.BooleanVar(master=top, value=config.show_osd)

    frame = tk.Frame(top, bg=card_color, highlightthickness=1, highlightbackground="#45475a")
    frame.pack(fill="both", expand=True, padx=15, pady=10)

    # Camera selection
    row1 = tk.Frame(frame, bg=card_color)
    row1.pack(fill="x", padx=10, pady=10)
    tk.Label(row1, text="Camera:", bg=card_color, fg=text_color, font=label_font).pack(side="left")
    camera_combo = ttk.Combobox(row1, textvariable=camera_idx_var, values=["0", "1", "2", "3", "4", "5"], width=5, state="readonly")
    camera_combo.pack(side="right")

    # Speed
    row2 = tk.Frame(frame, bg=card_color)
    row2.pack(fill="x", padx=10, pady=10)
    tk.Label(row2, text="Pointer Speed:", bg=card_color, fg=text_color, font=label_font).pack(side="left")
    speed_scale = tk.Scale(
        row2, from_=1.0, to=10.0, resolution=0.5, orient="horizontal",
        variable=speed_var, bg=card_color, fg=text_color, troughcolor=entry_bg,
        activebackground=accent_color, highlightthickness=0, bd=0, showvalue=True
    )
    speed_scale.pack(side="right", fill="x", expand=True, padx=(10, 0))

    # OSD
    row3 = tk.Frame(frame, bg=card_color)
    row3.pack(fill="x", padx=10, pady=10)
    tk.Checkbutton(row3, text="Show On-Screen Display (OSD)", variable=osd_var, bg=card_color, fg=text_color, selectcolor=entry_bg, font=label_font).pack(anchor="w")

    def _save():
        import dataclasses
        new_camera = dataclasses.replace(config.camera, index=int(camera_idx_var.get()))
        new_pointer = dataclasses.replace(config.pointer, g_hi=speed_var.get())
        new_config = dataclasses.replace(
            config,
            camera=new_camera,
            pointer=new_pointer,
            show_osd=osd_var.get()
        )
        save_config(new_config)
        conf.ACTIVE_CONFIG = new_config
        top.destroy()

    btn_frame = tk.Frame(top, bg=bg_color)
    btn_frame.pack(fill="x", pady=10)
    
    save_btn = tk.Button(
        btn_frame, text="Save & Close", bg=accent_color, fg="#11111b",
        font=(font_family, 10, "bold"), bd=0, padx=20, pady=5,
        command=_save
    )
    save_btn.pack(pady=5)
