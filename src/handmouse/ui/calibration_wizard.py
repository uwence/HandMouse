from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import messagebox, ttk
import time

from handmouse.config import (
    AppConfig,
    ExtendedGestureConfig,
    save_config,
)
from handmouse.ui.calibration_state import STATE as calibration_state

_wizard_window = None

class CalibrationWizard:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.top = tk.Toplevel(root)
        self.top.title("HandMouse Calibration Wizard")
        self.top.geometry("460x500")
        self.top.resizable(False, False)

        # Colors (mocha theme)
        self.bg_color = "#1e1e2e"
        self.card_color = "#252538"
        self.text_color = "#cdd6f4"
        self.accent_color = "#89b4fa"
        self.entry_bg = "#313244"
        self.button_hover = "#b4befe"
        self.muted_color = "#6c7086"
        self.success_color = "#a6e3a1"

        self.top.configure(bg=self.bg_color)

        self.font_family = "Segoe UI"
        self.title_font = ("Segoe UI", 14, "bold")
        self.section_font = ("Segoe UI", 11, "bold")
        self.label_font = ("Segoe UI", 10)
        self.button_font = ("Segoe UI", 10, "bold")

        # Steps: 1 = Intro, 2 = Open Hand, 3 = Pinch Close, 4 = Summary
        self.current_step = 1

        self.open_hand_ratio = None
        self.pinch_ratio = None

        self.is_capturing = False
        self.capture_time_left = 0
        self.captured_samples = []

        # UI structures
        self._build_header()
        self.content_frame = tk.Frame(self.top, bg=self.bg_color)
        self.content_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self.nav_frame = tk.Frame(self.top, bg=self.bg_color)
        self.nav_frame.pack(fill="x", side="bottom", padx=20, pady=15)

        self._build_navigation()
        self._show_step(1)

        # Start updating live metrics
        self.top.after(100, self._update_live_data)

        def _cleanup():
            global _wizard_window
            _wizard_window = None
            calibration_state.stop()
            self.top.destroy()

        self.top.protocol("WM_DELETE_WINDOW", _cleanup)

    def _build_header(self):
        banner = tk.Canvas(self.top, height=55, bg=self.card_color, highlightthickness=0)
        banner.pack(fill="x", pady=(0, 10))
        banner.create_rectangle(0, 51, 460, 55, fill=self.accent_color, outline="")
        banner.create_text(230, 28, text="CALIBRATION WIZARD", fill=self.text_color, font=self.title_font)

    def _build_navigation(self):
        self.cancel_btn = tk.Button(
            self.nav_frame, text="Cancel", font=self.button_font, bg="#45475a", fg=self.text_color,
            activebackground="#585b70", activeforeground=self.text_color, bd=0, relief="flat",
            padx=15, pady=6, command=self._on_cancel, cursor="hand2"
        )
        self.cancel_btn.pack(side="left")

        self.next_btn = tk.Button(
            self.nav_frame, text="Next", font=self.button_font, bg=self.accent_color, fg=self.bg_color,
            activebackground=self.button_hover, activeforeground=self.bg_color, bd=0, relief="flat",
            padx=15, pady=6, command=self._on_next, cursor="hand2"
        )
        self.next_btn.pack(side="right")

        self.prev_btn = tk.Button(
            self.nav_frame, text="Back", font=self.button_font, bg="#45475a", fg=self.text_color,
            activebackground="#585b70", activeforeground=self.text_color, bd=0, relief="flat",
            padx=15, pady=6, command=self._on_prev, cursor="hand2"
        )
        # Pack dynamically based on step

    def _show_step(self, step_idx):
        self.current_step = step_idx
        
        # Clear content frame
        for child in self.content_frame.winfo_children():
            child.destroy()

        if self.current_step == 1:
            self._render_step_1()
        elif self.current_step == 2:
            self._render_step_2()
        elif self.current_step == 3:
            self._render_step_3()
        elif self.current_step == 4:
            self._render_step_4()

        self._update_nav_buttons()

    def _update_nav_buttons(self):
        self.prev_btn.pack_forget()
        if self.current_step > 1:
            self.prev_btn.pack(side="right", padx=(0, 10))
            self.next_btn.pack_forget()
            self.next_btn.pack(side="right")

        if self.current_step == 1:
            self.next_btn.config(text="Get Started", state="normal")
        elif self.current_step in (2, 3):
            self.next_btn.config(text="Next")
            # Only enable Next if we have data for that step
            data_ok = (self.current_step == 2 and self.open_hand_ratio is not None) or \
                      (self.current_step == 3 and self.pinch_ratio is not None)
            self.next_btn.config(state="normal" if data_ok else "disabled")
        elif self.current_step == 4:
            self.next_btn.config(text="Apply & Save", state="normal")

    def _render_step_1(self):
        card = tk.Frame(self.content_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        card.pack(fill="both", expand=True, ipady=10)

        title = tk.Label(card, text="Optimize Your HandMouse", bg=self.card_color, fg=self.accent_color, font=self.section_font)
        title.pack(anchor="w", padx=15, pady=(15, 10))

        intro_text = (
            "Welcome to the HandMouse Calibration Wizard!\n\n"
            "This wizard will calibrate the algorithm to adapt to your specific:\n"
            "• Hand physical dimensions\n"
            "• Camera distance & Field of View\n"
            "• Light levels & Tracking conditions\n\n"
            "We will collect data for two hand postures:\n"
            "1. Fully open hand (Palm flat)\n"
            "2. Pinched fingers (Left click gesture)\n\n"
            "Please ensure your webcam is running and your hand is in view before proceeding."
        )
        lbl = tk.Label(card, text=intro_text, bg=self.card_color, fg=self.text_color, font=self.label_font, justify="left")
        lbl.pack(anchor="w", padx=15, pady=5)

    def _render_step_2(self):
        card = tk.Frame(self.content_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        card.pack(fill="both", expand=True, ipady=10)

        title = tk.Label(card, text="Step 1: Open Hand Calibration", bg=self.card_color, fg=self.accent_color, font=self.section_font)
        title.pack(anchor="w", padx=15, pady=(15, 10))

        inst_text = (
            "1. Keep your hand completely flat with fingers spread wide.\n"
            "2. Hold it at your normal operating distance from the camera.\n"
            "3. Click 'Start Capture' and keep your hand still for 3 seconds."
        )
        lbl = tk.Label(card, text=inst_text, bg=self.card_color, fg=self.text_color, font=self.label_font, justify="left")
        lbl.pack(anchor="w", padx=15, pady=5)

        # Status & live metrics
        self.live_status_frame = tk.Frame(card, bg=self.card_color)
        self.live_status_frame.pack(fill="x", padx=15, pady=15)

        self.live_metrics_lbl = tk.Label(
            self.live_status_frame, text="Live Ratio: --- | Span: ---", 
            bg=self.card_color, fg=self.text_color, font=self.label_font
        )
        self.live_metrics_lbl.pack(anchor="w")

        self.tracking_status_lbl = tk.Label(
            self.live_status_frame, text="Webcam Status: Waiting...", 
            bg=self.card_color, fg=self.muted_color, font=self.label_font
        )
        self.tracking_status_lbl.pack(anchor="w", pady=(2, 0))

        # Capture button
        self.capture_btn = tk.Button(
            card, text="Start Capture", font=self.button_font, bg=self.accent_color, fg=self.bg_color,
            activebackground=self.button_hover, activeforeground=self.bg_color, bd=0, relief="flat",
            padx=15, pady=8, command=self._start_capture_sequence, cursor="hand2"
        )
        self.capture_btn.pack(pady=15)

        # Result display
        self.result_lbl = tk.Label(card, text="", bg=self.card_color, fg=self.success_color, font=self.label_font)
        self.result_lbl.pack(pady=5)
        
        if self.open_hand_ratio is not None:
            self.result_lbl.config(text=f"Captured Open Hand Ratio: {self.open_hand_ratio:.3f}")

    def _render_step_3(self):
        card = tk.Frame(self.content_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        card.pack(fill="both", expand=True, ipady=10)

        title = tk.Label(card, text="Step 2: Pinch Close Calibration", bg=self.card_color, fg=self.accent_color, font=self.section_font)
        title.pack(anchor="w", padx=15, pady=(15, 10))

        inst_text = (
            "1. Press your thumb and index finger firmly together (Pinch Click).\n"
            "2. Keep the other fingers relaxed but make sure the pinch is clear.\n"
            "3. Click 'Start Capture' and hold the pinch still for 3 seconds."
        )
        lbl = tk.Label(card, text=inst_text, bg=self.card_color, fg=self.text_color, font=self.label_font, justify="left")
        lbl.pack(anchor="w", padx=15, pady=5)

        # Status & live metrics
        self.live_status_frame = tk.Frame(card, bg=self.card_color)
        self.live_status_frame.pack(fill="x", padx=15, pady=15)

        self.live_metrics_lbl = tk.Label(
            self.live_status_frame, text="Live Ratio: --- | Span: ---", 
            bg=self.card_color, fg=self.text_color, font=self.label_font
        )
        self.live_metrics_lbl.pack(anchor="w")

        self.tracking_status_lbl = tk.Label(
            self.live_status_frame, text="Webcam Status: Waiting...", 
            bg=self.card_color, fg=self.muted_color, font=self.label_font
        )
        self.tracking_status_lbl.pack(anchor="w", pady=(2, 0))

        # Capture button
        self.capture_btn = tk.Button(
            card, text="Start Capture", font=self.button_font, bg=self.accent_color, fg=self.bg_color,
            activebackground=self.button_hover, activeforeground=self.bg_color, bd=0, relief="flat",
            padx=15, pady=8, command=self._start_capture_sequence, cursor="hand2"
        )
        self.capture_btn.pack(pady=15)

        # Result display
        self.result_lbl = tk.Label(card, text="", bg=self.card_color, fg=self.success_color, font=self.label_font)
        self.result_lbl.pack(pady=5)
        
        if self.pinch_ratio is not None:
            self.result_lbl.config(text=f"Captured Pinch Ratio: {self.pinch_ratio:.3f}")

    def _render_step_4(self):
        card = tk.Frame(self.content_frame, bg=self.card_color, bd=0, highlightthickness=1, highlightbackground="#45475a")
        card.pack(fill="both", expand=True, ipady=10)

        title = tk.Label(card, text="Step 3: Summary & Application", bg=self.card_color, fg=self.accent_color, font=self.section_font)
        title.pack(anchor="w", padx=15, pady=(15, 10))

        # Perform mathematical recommendations
        # Open: O, Pinch: P
        O = self.open_hand_ratio
        P = self.pinch_ratio
        span_range = O - P

        # Close threshold is recommended at 30% of range above Pinch
        rec_close = P + 0.3 * span_range
        # Open threshold is recommended at 50% of range above Pinch
        rec_open = P + 0.5 * span_range

        self.rec_close = round(rec_close, 3)
        self.rec_open = round(rec_open, 3)

        desc = (
            f"Wizard completed! Summary of measurements:\n\n"
            f"• Average Open Hand Ratio (Baseline):  {O:.3f}\n"
            f"• Average Pinch Close Ratio:           {P:.3f}\n"
            f"• Usable range window size:            {span_range:.3f}\n\n"
            f"Recommendations for your hand profile:\n"
            f"• Pinch Close Threshold:               {self.rec_close:.3f}\n"
            f"• Pinch Open Threshold:                {self.rec_open:.3f}\n\n"
            "Clicking 'Apply & Save' will write these values into your YAML profile configuration and immediately update the running system."
        )

        lbl = tk.Label(card, text=desc, bg=self.card_color, fg=self.text_color, font=("Consolas", 10), justify="left")
        lbl.pack(anchor="w", padx=15, pady=10)

    def _start_capture_sequence(self):
        if self.is_capturing:
            return
        
        self.is_capturing = True
        self.capture_time_left = 3.0
        self.captured_samples = []
        self.capture_btn.config(state="disabled", text="Capturing...")
        self.prev_btn.config(state="disabled")
        self.next_btn.config(state="disabled")

        calibration_state.start()
        self._capture_tick()

    def _capture_tick(self):
        if self.capture_time_left <= 0:
            self._end_capture_sequence()
            return

        # Read samples
        avg, min_r, max_r = calibration_state.get_summary()
        with calibration_state.lock:
            # Transfer samples
            self.captured_samples.extend(calibration_state.captured_ratios)
            calibration_state.captured_ratios.clear()

        self.capture_time_left -= 0.1
        self.capture_btn.config(text=f"Capturing... {max(0.0, self.capture_time_left):.1f}s")
        self.top.after(100, self._capture_tick)

    def _end_capture_sequence(self):
        calibration_state.stop()
        self.is_capturing = False

        self.capture_btn.config(state="normal", text="Re-capture")
        self.prev_btn.config(state="normal")

        # Process captured samples
        valid_samples = [s for s in self.captured_samples if s > 0.0]
        if not valid_samples:
            messagebox.showerror(
                "Calibration Error",
                "No hand coordinates were detected during the capture window.\n\n"
                "Please check:\n"
                "1. Is your hand in the camera's FOV?\n"
                "2. Is the webcam active?\n"
                "3. Ensure the room has sufficient light.",
                parent=self.top
            )
            self.result_lbl.config(text="Capture failed: Hand not detected.", fg="#f38ba8")
            self._update_nav_buttons()
            return

        avg_ratio = sum(valid_samples) / len(valid_samples)

        if self.current_step == 2:
            self.open_hand_ratio = avg_ratio
            self.result_lbl.config(
                text=f"Successfully captured open hand ratio: {self.open_hand_ratio:.3f}",
                fg=self.success_color
            )
        elif self.current_step == 3:
            self.pinch_ratio = avg_ratio
            self.result_lbl.config(
                text=f"Successfully captured pinch ratio: {self.pinch_ratio:.3f}",
                fg=self.success_color
            )

        self._update_nav_buttons()

    def _update_live_data(self):
        if not self.top.winfo_exists():
            return

        if self.current_step in (2, 3):
            # Fetch live metrics
            ratio = calibration_state.last_pinch_ratio
            span = calibration_state.last_palm_span

            if ratio > 0.0:
                self.live_metrics_lbl.config(text=f"Live Pinch Ratio: {ratio:.3f} | Palm Span: {span:.3f}")
                self.tracking_status_lbl.config(text="Webcam Status: Tracking Active (Hand detected)", fg=self.success_color)
            else:
                self.live_metrics_lbl.config(text="Live Ratio: --- | Span: ---")
                self.tracking_status_lbl.config(text="Webcam Status: Hand Not Found", fg=self.muted_color)

        self.top.after(100, self._update_live_data)

    def _on_next(self):
        if self.current_step == 1:
            self._show_step(2)
        elif self.current_step == 2:
            self._show_step(3)
        elif self.current_step == 3:
            self._show_step(4)
        elif self.current_step == 4:
            self._apply_and_save()

    def _on_prev(self):
        if self.current_step > 1:
            self._show_step(self.current_step - 1)

    def _on_cancel(self):
        global _wizard_window
        _wizard_window = None
        calibration_state.stop()
        self.top.destroy()

    def _apply_and_save(self):
        import handmouse.config as conf
        config = conf.ACTIVE_CONFIG

        # Build new config with updated gesture settings
        new_config = AppConfig(
            camera=config.camera,
            view=config.view,
            pointer=config.pointer,
            shortcut=config.shortcut,
            clutch=config.clutch,
            gesture_switches=config.gesture_switches,
            gesture_config=ExtendedGestureConfig(
                pinch_close_ratio=self.rec_close,
                pinch_open_ratio=self.rec_open,
            ),
            grab_scroll_config=config.grab_scroll_config,
            show_osd=config.show_osd,
        )

        save_config(new_config)
        conf.ACTIVE_CONFIG = new_config

        messagebox.showinfo(
            "Success",
            "HandMouse calibration finished successfully!\n\n"
            f"Pinch thresholds applied:\n"
            f"• Pinch Close Ratio: {self.rec_close:.3f}\n"
            f"• Pinch Open Ratio: {self.rec_open:.3f}",
            parent=self.top
        )

        global _wizard_window
        _wizard_window = None
        self.top.destroy()


def _build_wizard_ui(root) -> None:
    global _wizard_window
    if _wizard_window is not None and _wizard_window.top.winfo_exists():
        _wizard_window.top.lift()
        _wizard_window.top.focus_force()
        return

    _wizard_window = CalibrationWizard(root)
