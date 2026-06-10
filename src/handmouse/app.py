from __future__ import annotations

import argparse
import json
import time
import threading
from typing import Any

from handmouse.camera import Camera
from handmouse.clutch_input import ClutchSnapshot, GlobalClutchInput
from handmouse.config import DEFAULT_CONFIG, load_or_create_config
from handmouse.debug_view import DebugTelemetry, DebugView
from handmouse.engagement import EngagementConfig, EngagementFSM
from handmouse.gesture_detector import GestureConfig, GestureDetector, GestureState
from handmouse.grab_scroll_detector import (
    GrabScrollConfig,
    GrabScrollDetector,
    GrabScrollResult,
    GrabScrollState,
)
from handmouse.interlock import InteractionInterlock
from handmouse.hand_tracker import HandTracker
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.move_mode import (
    MoveModeConfig,
    MoveModeController,
    MoveModeResult,
    MoveModeState,
)
from handmouse.pointer_engine import PointerEngine, PointerEngineConfig
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutDetector, ShortcutAction
from handmouse.thread_pipeline import CameraReader, InferenceWorker
from handmouse.alt_tab_detector import AltTabDetector, AltTabState
import handmouse.coordinate_mapper as coordinate_mapper


WINDOW_NAME = "HandMouse"
PENDING_STATE_TOGGLE = False
SHOULD_EXIT = False

def main() -> None:
    parser = argparse.ArgumentParser(description=WINDOW_NAME)
    parser.add_argument("--record-telemetry", type=str, default=None, help="Path to dump frame telemetry JSONL")
    args = parser.parse_args()

    import handmouse.config as conf
    config = conf.ACTIVE_CONFIG
    cv2 = _load_cv2()
    screen_size = _screen_size()
    if screen_size is None:
        screen_w, screen_h = 1920, 1080
    else:
        screen_w, screen_h = screen_size

    camera = Camera(config.camera)
    tracker: HandTracker | None = None
    mouse = MouseController()
    shortcut = ShortcutController()
    clutch_input = GlobalClutchInput(config.clutch.key_name)

    try:
        camera.open()
        tracker = HandTracker(num_hands=1)

        pointer = PointerEngine(
            PointerEngineConfig(
                screen_width=screen_w,
                screen_height=screen_h,
                control_region=config.pointer.control_region,
                g_hi=config.pointer.g_hi,
            )
        )
        interlock = InteractionInterlock()
        gesture = GestureDetector(
            GestureConfig(
                pinch_close=config.gesture_config.pinch_close,
                pinch_open=config.gesture_config.pinch_open,
            ),
            interlock=interlock
        )
        grab_scroll = GrabScrollDetector(
            GrabScrollConfig(
                scroll_sensitivity=config.grab_scroll_config.scroll_sensitivity
            ),
            interlock=interlock
        )
        shortcut_detector = ShortcutDetector(config.shortcut)
        alt_tab_detector = AltTabDetector()
        engagement = EngagementFSM(EngagementConfig())
        move_mode = MoveModeController(MoveModeConfig())
        debug_view = DebugView(config)
        
        from handmouse.osd import OSDManager
        osd = OSDManager(enabled=config.show_osd)
        
        try:
            clutch_input.start()
            clutch_status = "OK"
        except Exception as exc:
            clutch_status = "FAILED"
            print(f"WARNING: Global clutch input listener failed to start: {exc}")

        camera_reader = CameraReader(camera)
        inference_worker = InferenceWorker(camera_reader, tracker)
        camera_reader.start()
        inference_worker.start()

        telemetry_file = None
        if args.record_telemetry:
            telemetry_file = open(args.record_telemetry, "w", encoding="utf-8")
            
        def run_cv2_app():
            try:
                _run_loop(
                    cv2=cv2,
                    camera=camera,
                    tracker=tracker,
                    pointer=pointer,
                    gesture=gesture,
                    grab_scroll=grab_scroll,
                    shortcut_detector=shortcut_detector,
                    engagement=engagement,
                    mouse=mouse,
                    shortcut=shortcut,
                    debug_view=debug_view,
                    clutch_input=clutch_input,
                    move_mode=move_mode,
                    clutch_status=clutch_status,
                    telemetry_file=telemetry_file,
                    camera_reader=camera_reader,
                    inference_worker=inference_worker,
                    alt_tab_detector=alt_tab_detector,
                    osd=osd,
                )
            except Exception as e:
                print(f"Error in HandMouse loop: {e}")
            finally:
                try:
                    from handmouse.tray import stop_tray_icon
                    stop_tray_icon()
                except Exception:
                    pass
                if telemetry_file:
                    telemetry_file.close()
                inference_worker.stop()
                camera_reader.stop()
                inference_worker.join(timeout=1.0)
                camera_reader.join(timeout=1.0)
        
        app_thread = threading.Thread(target=run_cv2_app, daemon=True)
        app_thread.start()

        try:
            from handmouse.tray import start_tray_icon_blocking
            start_tray_icon_blocking()
        except Exception as exc:
            import traceback
            err_msg = traceback.format_exc()
            print(f"WARNING: System tray failed to start: {exc}")
            
            # Show a visible error box to the user so we can debug this!
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "HandMouse Tray Error", 
                f"Failed to start system tray icon.\n\nError:\n{exc}\n\nDetails:\n{err_msg}"
            )
            root.destroy()
            
            # Fallback if tray completely fails
            while app_thread.is_alive():
                app_thread.join(1.0)
    finally:
        if "alt_tab_detector" in locals():
            alt_tab_detector.reset()
        mouse.set_control_enabled(False)
        shortcut.set_enabled(False)
        clutch_input.stop()
        camera.release()
        if tracker is not None:
            tracker.close()
        cv2.destroyAllWindows()


def _run_loop(
    *,
    cv2: Any,
    camera: Camera,
    tracker: HandTracker,
    pointer: PointerEngine,
    gesture: GestureDetector,
    grab_scroll: GrabScrollDetector,
    shortcut_detector: ShortcutDetector,
    engagement: EngagementFSM,
    mouse: MouseController,
    shortcut: ShortcutController,
    debug_view: DebugView,
    clutch_input: Any | None = None,
    move_mode: Any | None = None,
    clutch_status: str | None = None,
    telemetry_file: Any | None = None,
    camera_reader: CameraReader | None = None,
    inference_worker: InferenceWorker | None = None,
    alt_tab_detector: AltTabDetector | None = None,
    osd: Any | None = None,
) -> None:
    previous_frame_time = time.perf_counter()
    previous_frame_capture_time = previous_frame_time
    palm_visible_start_ms: int | None = None
    last_m_state = False
    last_q_state = False
    pending_m_press = False
    drag_active = False
    pinch_start_point = None
    last_frame_time_ms = 0
    grab_release_cooldown_until = 0
    was_alt_tab_active = False
    was_grabbing = False

    last_applied_config = None
    last_active_state = None

    import handmouse.config as conf

    while True:
        global SHOULD_EXIT
        if SHOULD_EXIT:
            break

        config = conf.ACTIVE_CONFIG
        if config is not last_applied_config:
            last_applied_config = _apply_runtime_settings(
                pointer=pointer,
                gesture=gesture,
                grab_scroll=grab_scroll,
                shortcut_detector=shortcut_detector,
                debug_view=debug_view,
                config=config,
                last_applied_config=last_applied_config,
                osd=osd,
            )

        if inference_worker is not None and camera_reader is not None:
            # Multi-threaded path
            has_new = inference_worker.buffer.wait_new_result(timeout=0.010)

            if not has_new:
                # Pump OpenCV events to remain responsive
                raw_key = cv2.waitKey(1) & 0xFF
                if raw_key == ord("q"):
                    break
                if raw_key == ord("m"):
                    pending_m_press = True
                continue

            inference_worker.buffer.clear()
            hand_result, frame, now_ms = inference_worker.buffer.get()
            if frame is None or hand_result is None:
                continue

            raw_hand_result = hand_result
            hand_result = coordinate_mapper.unify_hand_result(raw_hand_result, conf.ACTIVE_CONFIG.camera.input_is_mirrored)

            now = time.perf_counter()
            frame_capture_time = now_ms / 1000.0
            frame_age_ms = int((now - frame_capture_time) * 1000)
            fps = _fps(previous_frame_time, now)
            previous_frame_time = now
        else:
            # Synchronous fallback path (used in tests)
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError(
                    "Could not read a frame from the camera. Check Windows camera "
                    "permissions, close other apps using the camera, or change the "
                    "camera index in DEFAULT_CONFIG."
                )

            now = time.perf_counter()
            frame_capture_time = now
            frame_age_ms = int((now - previous_frame_capture_time) * 1000)
            previous_frame_capture_time = frame_capture_time
            now_ms = int(now * 1000)
            fps = _fps(previous_frame_time, now)
            previous_frame_time = now

            hand_result = tracker.process(frame, frame_timestamp_ms=now_ms)
            
        raw_hand_result = hand_result
        hand_result = coordinate_mapper.unify_hand_result(raw_hand_result, conf.ACTIVE_CONFIG.camera.input_is_mirrored)
        
        hand_missing = not hand_result or not hand_result.landmarks

        landmarks = hand_result.landmarks if hand_result else None
        palm_visible = _is_palm_open(landmarks)
        vsign_visible = _is_vsign_open(landmarks)
        if palm_visible:
            if palm_visible_start_ms is None:
                palm_visible_start_ms = now_ms
            palm_hold_ms = now_ms - palm_visible_start_ms
        else:
            palm_visible_start_ms = None
            palm_hold_ms = 0

        raw_key = cv2.waitKey(1) & 0xFF
        m_pressed_edge = _is_key_pressed_edge(raw_key, ord("m"), last_m_state)
        q_pressed_edge = _is_key_pressed_edge(raw_key, ord("q"), last_q_state)
        last_m_state = raw_key == ord("m")
        last_q_state = raw_key == ord("q")

        global PENDING_STATE_TOGGLE
        if PENDING_STATE_TOGGLE:
            m_pressed_edge = True
            PENDING_STATE_TOGGLE = False

        if inference_worker is not None and camera_reader is not None:
            m_pressed_edge = m_pressed_edge or pending_m_press
            pending_m_press = False

        engagement_result = engagement.update(
            hotkey_pressed=m_pressed_edge,
            palm_visible=palm_visible,
            palm_hold_ms=palm_hold_ms,
            hand_missing=hand_missing,
            escape_requested=q_pressed_edge,
            now_ms=now_ms,
        )

        if engagement_result.is_active != last_active_state:
            try:
                from handmouse.tray import update_tray_status
                update_tray_status(engagement_result.is_active)
            except Exception:
                pass
            last_active_state = engagement_result.is_active

        if q_pressed_edge:
            break

        is_active = engagement_result.is_active
        if is_active and hand_result.landmarks:
            label = getattr(hand_result, "handedness_label", None)
            if not _is_palm_facing_camera(hand_result.landmarks, label):
                # Treat sideways or back-facing hands as inactive for gestures and cursor movement
                is_active = False

        mouse.set_control_enabled(is_active)
        shortcut.set_enabled(is_active)
        clutch_snapshot = _clutch_snapshot(clutch_input)
        move_pose = _is_move_pose(hand_result.landmarks)
        move_mode_result = _move_mode_result(
            move_mode=move_mode,
            is_active=is_active,
            clutch_down=clutch_snapshot.clutch_down,
            move_pose=move_pose,
            now_ms=now_ms,
        )
        move_active = is_active and move_mode_result.movement_enabled
        shortcut_should_reset = False
        dx, dy = 0.0, 0.0

        try:
            if move_active:
                if alt_tab_detector is not None:
                    alt_tab_detector.reset()
                if drag_active:
                    mouse.left_up()
                    drag_active = False
                delta = pointer.update(hand_result, now_ms)
                if delta is not None and (delta.dx != 0 or delta.dy != 0):
                    mouse.move_relative(delta)
                    dx = delta.dx
                    dy = delta.dy
                gesture_result = gesture.update(None, None, now_ms)
                grab_scroll.reset()
                grab_result = _neutral_grab_result()
                shortcut_should_reset = True
            elif is_active and not clutch_snapshot.clutch_down:
                alt_tab_active = False
                import handmouse.config as conf
                if alt_tab_detector is not None and conf.ACTIVE_CONFIG.gesture_switches.alt_tab:
                    alt_tab_state, is_alt_held = alt_tab_detector.update(hand_result.landmarks, now_ms)
                    if alt_tab_state == AltTabState.ACTIVE or is_alt_held:
                        alt_tab_active = True
                        if not was_alt_tab_active and osd is not None:
                            osd.show_text("Task View")
                was_alt_tab_active = alt_tab_active

                if alt_tab_active:
                    if drag_active:
                        mouse.left_up()
                        drag_active = False
                    pointer.reset()
                    gesture_result = gesture.update(None, None, now_ms)
                    grab_scroll.reset()
                    grab_result = _neutral_grab_result()
                    shortcut_should_reset = True
                else:
                    pointer.reset()
                    thumb_tip = hand_result.thumb_tip
                    index_tip = hand_result.index_tip
                    middle_tip = None
                    if hand_result.landmarks and len(hand_result.landmarks) > 12:
                        middle_tip = hand_result.landmarks[12]

                    # Heuristic to prevent false pinches when fingers are curled into a fist
                    if _is_finger_curled(hand_result.landmarks, 5, 8):
                        index_tip = None
                    if _is_finger_curled(hand_result.landmarks, 9, 12):
                        middle_tip = None

                    gesture_result = gesture.update(
                        thumb_tip,
                        index_tip,
                        now_ms,
                        middle=middle_tip,
                    )
                    grab_result = grab_scroll.update(hand_result.landmarks, now_ms)
                    
                    is_grabbing = grab_result.state in (GrabScrollState.GRABBING, GrabScrollState.DRAGGING)
                    if is_grabbing and not was_grabbing and osd is not None:
                        osd.show_text("Scroll")
                    was_grabbing = is_grabbing

                    # Drag & Drop logic
                    if gesture_result.state == GestureState.PINCH_PRESSED:
                        pinch_start_point = index_tip
                    elif gesture_result.state == GestureState.PINCH_HOLD and conf.ACTIVE_CONFIG.gesture_switches.drag_drop:
                        if not drag_active and pinch_start_point is not None and index_tip is not None:
                            dist = ((index_tip.x - pinch_start_point.x) ** 2 + 
                                    (index_tip.y - pinch_start_point.y) ** 2) ** 0.5
                            if dist > 0.04:  # drag threshold
                                drag_active = True
                                mouse.left_down()
                                if osd is not None: osd.show_text("Drag")
                        
                        if drag_active:
                            delta = pointer.update(hand_result, now_ms)
                            if delta is not None and (delta.dx != 0 or delta.dy != 0):
                                mouse.move_relative(delta)
                                dx = delta.dx
                                dy = delta.dy

                    if gesture_result.state not in (GestureState.PINCH_PRESSED, GestureState.PINCH_HOLD, GestureState.COOLDOWN):
                        if drag_active:
                            mouse.left_up()
                            drag_active = False

                    if gesture_result.should_click or gesture_result.should_double_click:
                        if drag_active:
                            mouse.left_up()
                            drag_active = False
                        else:
                            if gesture_result.should_double_click and conf.ACTIVE_CONFIG.gesture_switches.double_click:
                                mouse.double_click()
                                if osd is not None: osd.show_text("Double Click")
                            else:
                                mouse.left_click()
                                if osd is not None: osd.show_text("Click")

                    if gesture_result.should_right_click and conf.ACTIVE_CONFIG.gesture_switches.right_click:
                        if drag_active:
                            mouse.left_up()
                            drag_active = False
                        mouse.right_click()
                        if osd is not None: osd.show_text("Right Click")
            else:
                if alt_tab_detector is not None:
                    alt_tab_detector.reset()
                if drag_active:
                    mouse.left_up()
                    drag_active = False
                gesture_result = gesture.update(None, None, now_ms)
                pointer.reset()
                grab_scroll.reset()
                grab_result = _neutral_grab_result()
                shortcut_should_reset = True
            if is_active and not clutch_snapshot.clutch_down and grab_result.scroll_delta != 0:
                shortcut.scroll(grab_result.scroll_delta)
                
            if grab_result.is_grab_pose:
                grab_release_cooldown_until = now_ms + 800

            if shortcut_should_reset or move_active or clutch_snapshot.clutch_down:
                shortcut_detector.reset()
            elif not is_active or hand_result.index_tip is None or grab_result.is_grab_pose or now_ms < grab_release_cooldown_until:
                shortcut_detector.reset()
            else:
                shortcut_result = shortcut_detector.update(hand_result.index_tip, now_ms, palm_open=palm_visible)
                if shortcut_result.action is not None:
                    is_palm_swipe = shortcut_result.action in (ShortcutAction.SWIPE_LEFT_PALM, ShortcutAction.SWIPE_RIGHT_PALM)
                    if not is_palm_swipe or conf.ACTIVE_CONFIG.gesture_switches.win_d:
                        shortcut.execute(shortcut_result.action)
                        if osd is not None:
                            action_names = {
                                ShortcutAction.SWIPE_LEFT_PALM: "Desktop (Win+D)",
                                ShortcutAction.SWIPE_RIGHT_PALM: "Desktop (Win+D)",
                                ShortcutAction.SWIPE_UP: "Scroll Down",
                                ShortcutAction.SWIPE_DOWN: "Scroll Up",
                                ShortcutAction.SWIPE_LEFT: "Back",
                                ShortcutAction.SWIPE_RIGHT: "Forward",
                            }
                            if shortcut_result.action in action_names:
                                osd.show_text(action_names[shortcut_result.action])
        except Exception as exc:
            if _is_failsafe_abort(exc):
                _abort_control(
                    mouse=mouse,
                    shortcut=shortcut,
                    engagement=engagement,
                    gesture=gesture,
                    pointer=pointer,
                    shortcut_detector=shortcut_detector,
                    alt_tab_detector=alt_tab_detector,
                )
                break
            raise

        telemetry = DebugTelemetry(
            fps=fps,
            frame_age_ms=frame_age_ms,
            backend_name=camera.backend_name,
            pointer=pointer,
            engagement=engagement_result,
            grab_scroll=grab_result,
            clutch_down=clutch_snapshot.clutch_down,
            clutch_status=clutch_status,
            move_mode=move_mode_result.state.name,
            move_pose=move_mode_result.move_pose,
        )

        debug_frame = debug_view.draw(
            frame,
            raw_hand_result,
            gesture_result,
            is_active,
            telemetry,
        )

        cv2.imshow(WINDOW_NAME, debug_frame)

        if telemetry_file is not None:
            telemetry_data = {
                "frame_capture_time": frame_capture_time,
                "frame_age_ms": frame_age_ms,
                "pointer_dx": dx,
                "pointer_dy": dy,
                "engagement_active": is_active,
                "click_triggered": gesture_result.should_click,
                "scroll_delta": grab_result.scroll_delta,
                "clutch_down": clutch_snapshot.clutch_down,
                "move_mode": move_mode_result.state.name,
            }
            telemetry_file.write(json.dumps(telemetry_data) + "\n")
            telemetry_file.flush()

def _apply_runtime_settings(
    *,
    pointer: PointerEngine,
    gesture: GestureDetector,
    grab_scroll: GrabScrollDetector,
    shortcut_detector: ShortcutDetector,
    debug_view: DebugView,
    config: AppConfig,
    last_applied_config: AppConfig | None,
    osd: Any | None = None,
) -> AppConfig:
    # Update pointer config
    if hasattr(pointer, "config") and hasattr(pointer.config, "screen_width"):
        pointer.config = PointerEngineConfig(
            screen_width=pointer.config.screen_width,
            screen_height=pointer.config.screen_height,
            control_region=config.pointer.control_region,
            g_hi=config.pointer.g_hi,
        )
    # Update gesture config
    if hasattr(gesture, "config"):
        gesture.config = GestureConfig(
            pinch_close=config.gesture_config.pinch_close,
            pinch_open=config.gesture_config.pinch_open,
        )
    # Update grab scroll config
    if hasattr(grab_scroll, "config"):
        grab_scroll.config = GrabScrollConfig(
            scroll_sensitivity=config.grab_scroll_config.scroll_sensitivity
        )
    # Update shortcut config
    if hasattr(shortcut_detector, "config"):
        shortcut_detector.config = config.shortcut
    # Update debug view config
    if hasattr(debug_view, "config"):
        debug_view.config = config
    # Update OSD config
    if osd is not None:
        osd.set_enabled(config.show_osd)

    return config


def _is_key_pressed_edge(raw_key: int, target: int, last_state: bool) -> bool:
    """Treat any non-zero key match within this frame as a press edge.

    OpenCV waitKey does not expose key-up events, so we approximate a press
    edge with the frame's key. This means holding the key down will fire
    multiple edges across frames; the consumer (EngagementFSM) is responsible
    for handling repeated edges gracefully.
    """

    return raw_key == target and not last_state


def _is_palm_facing_camera(landmarks: list[Any] | None, handedness_label: str | None) -> bool:
    """Check if the palm is facing the camera using 2D aspect ratio and cross product heuristics.
    
    If the hand is sideways, the horizontal distance between index and pinky knuckles
    will be very small compared to the vertical distance from wrist to middle knuckle.
    
    Additionally, we use the 2D cross product of the wrist->index and wrist->pinky vectors
    to determine if the back of the hand is facing the camera based on handedness.
    """
    if not landmarks or len(landmarks) < 21:
        return False
        
    wrist = landmarks[0]
    index_mcp = landmarks[5]
    middle_mcp = landmarks[9]
    pinky_mcp = landmarks[17]

    def _dist(p1, p2):
        return ((p1.x - p2.x)**2 + (p1.y - p2.y)**2)**0.5

    palm_width = _dist(index_mcp, pinky_mcp)
    palm_height = _dist(wrist, middle_mcp)
    
    if palm_height == 0:
        return False
        
    # 1. Sideways check
    if (palm_width / palm_height) < 0.45:
        return False
        
    # 2. Back of hand check
    if handedness_label is not None:
        is_left = (handedness_label.lower() == "left")
        
        v1_x = index_mcp.x - wrist.x
        v1_y = index_mcp.y - wrist.y
        v2_x = pinky_mcp.x - wrist.x
        v2_y = pinky_mcp.y - wrist.y
        
        cross = v1_x * v2_y - v1_y * v2_x
        
        # In the Unified Physical Space (X increases physical right, Y increases physical down):
        # Physical Left Hand, Palm Facing: Thumb is Right, Pinky is Left -> Index is Right(x>0), Pinky is Left(x<0)
        # v1=(+x, -y), v2=(-x, -y) -> cross = (+)*(-) - (-)*(-) = (-) -> cross < 0
        # Physical Right Hand, Palm Facing: Thumb is Left, Pinky is Right -> Index is Left(x<0), Pinky is Right(x>0)
        # v1=(-x, -y), v2=(+x, -y) -> cross = (-)*(-) - (-)*(+) = (+) -> cross > 0
        # print(f"DEBUG: is_left={is_left}, cross={cross:.4f}")
        # Pass the metrics to some global debug state so we can render them on OSD
        debug_metrics = f"v1=({v1_x:.2f},{v1_y:.2f}) v2=({v2_x:.2f},{v2_y:.2f}) c={cross:.3f} L={is_left}"
        if not hasattr(coordinate_mapper, "DEBUG_CROSS"):
            coordinate_mapper.DEBUG_CROSS = ""
        coordinate_mapper.DEBUG_CROSS = debug_metrics

        if is_left:
            if cross <= 0:  # Back of left hand
                return False
        else:
            if cross >= 0:  # Back of right hand
                return False
        
        return True


def _is_finger_curled(landmarks: list[Any] | None, mcp_idx: int, tip_idx: int) -> bool:
    """Check if a finger is curled into a fist (tip closer to wrist than MCP)."""
    if not landmarks or len(landmarks) <= tip_idx:
        return False
        
    wrist = landmarks[0]
    mcp = landmarks[mcp_idx]
    tip = landmarks[tip_idx]
    
    def _dist(p1, p2):
        return ((p1.x - p2.x)**2 + (p1.y - p2.y)**2)**0.5
        
    dist_tip = _dist(wrist, tip)
    dist_mcp = _dist(wrist, mcp)
    
    # If the tip distance to wrist is barely larger than MCP distance, 
    # the finger is heavily curled inwards.
    return dist_tip < dist_mcp * 1.2


def _is_palm_open(landmarks: list[Any] | None) -> bool:
    """Loose open-palm heuristic: 4 fingertips further from palm center than MCPs."""

    if not landmarks or len(landmarks) < 21:
        return False

    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)

    fingertip_indices = (8, 12, 16, 20)
    mcp_indices = (5, 9, 13, 17)
    extended = 0
    for tip_i, mcp_i in zip(fingertip_indices, mcp_indices):
        def _dist(x1, y1, x2, y2):
            return ((x1 - x2)**2 + (y1 - y2)**2)**0.5
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d > 1.1:
            extended += 1
    return extended >= 3


def _is_vsign_open(landmarks: list[Any] | None) -> bool:
    """V-Sign heuristic: Index and middle extended, ring and pinky curled."""
    if not landmarks or len(landmarks) < 21:
        return False

    wrist = landmarks[0]
    index_tip = landmarks[8]
    middle_tip = landmarks[12]
    ring_tip = landmarks[16]
    pinky_tip = landmarks[20]

    def _dist(p1, p2):
        return ((p1.x - p2.x)**2 + (p1.y - p2.y)**2)**0.5

    dist_index = _dist(index_tip, wrist)
    dist_middle = _dist(middle_tip, wrist)
    dist_ring = _dist(ring_tip, wrist)
    dist_pinky = _dist(pinky_tip, wrist)

    return (dist_index > 0.3 and dist_middle > 0.3 and 
            dist_ring < 0.25 and dist_pinky < 0.25)


def _is_move_pose(landmarks: list[Any] | None) -> bool:
    if not landmarks or len(landmarks) < 21:
        return False

    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)

    extended = 0
    for tip_i, mcp_i in ((8, 5), (12, 9)):
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d > 1.2:
            extended += 1

    curled = 0
    for tip_i, mcp_i in ((16, 13), (20, 17)):
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d < 1.35:
            curled += 1

    return extended == 2 and curled >= 1


def _dist(ax: float, ay: float, bx: float, by: float) -> float:
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


def _is_grab_like_hand_pose(landmarks: list[Any] | None) -> bool:
    if not landmarks or len(landmarks) < 21:
        return False

    wrist = landmarks[0]
    middle_mcp = landmarks[9]
    palm_indices = (0, 5, 9, 13, 17)
    palm_x = sum(landmarks[i].x for i in palm_indices) / len(palm_indices)
    palm_y = sum(landmarks[i].y for i in palm_indices) / len(palm_indices)
    palm_scale = _dist(wrist.x, wrist.y, middle_mcp.x, middle_mcp.y)
    if palm_scale <= 0:
        return False

    thumb_tip = landmarks[4]
    index_tip = landmarks[8]
    thumb_index_ratio = _dist(thumb_tip.x, thumb_tip.y, index_tip.x, index_tip.y) / palm_scale
    if thumb_index_ratio > 1.8:
        return False

    curled = 0
    for mcp_i, tip_i in ((9, 12), (13, 16), (17, 20)):
        mcp_d = _dist(landmarks[mcp_i].x, landmarks[mcp_i].y, palm_x, palm_y)
        tip_d = _dist(landmarks[tip_i].x, landmarks[tip_i].y, palm_x, palm_y)
        if mcp_d > 0 and tip_d / mcp_d <= 1.85:
            curled += 1
    return curled >= 2


def _screen_size() -> tuple[int, int] | None:
    try:
        import pyautogui
    except Exception:
        return None
    try:
        width, height = pyautogui.size()
        return int(width), int(height)
    except Exception:
        return None


def _abort_control(
    *,
    mouse: MouseController,
    shortcut: ShortcutController,
    engagement: EngagementFSM,
    gesture: GestureDetector,
    pointer: PointerEngine,
    shortcut_detector: ShortcutDetector,
    alt_tab_detector: AltTabDetector | None = None,
) -> None:
    mouse.set_control_enabled(False)
    shortcut.set_enabled(False)
    engagement.force_idle()
    gesture.reset()
    pointer.reset()
    shortcut_detector.reset()
    if alt_tab_detector is not None:
        alt_tab_detector.reset()


def _is_failsafe_abort(exc: Exception) -> bool:
    return isinstance(exc, MouseFailsafeTriggered) or exc.__class__.__name__ == "FailSafeException"


def _clutch_snapshot(clutch_input: Any | None) -> ClutchSnapshot:
    if clutch_input is None:
        return ClutchSnapshot(clutch_down=False)
    return clutch_input.snapshot()


def _move_mode_result(
    *,
    move_mode: Any | None,
    is_active: bool,
    clutch_down: bool,
    move_pose: bool,
    now_ms: int,
) -> MoveModeResult:
    if move_mode is None:
        return MoveModeResult(
            state=MoveModeState.ACTIVE if is_active else MoveModeState.NEUTRAL,
            movement_enabled=is_active,
            move_pose=move_pose,
            clutch_down=clutch_down,
        )
    return move_mode.update(
        clutch_down=clutch_down,
        move_pose=move_pose,
        now_ms=now_ms,
    )


def _neutral_grab_result() -> GrabScrollResult:
    return GrabScrollResult(
        state=GrabScrollState.NO_HAND,
        active=False,
        scroll_delta=0,
        displacement_x=None,
        displacement_y=None,
        is_grab_pose=False,
    )


def _fps(previous_time: float, now: float) -> float:
    elapsed = now - previous_time
    if elapsed <= 0:
        return 0.0
    return 1.0 / elapsed


def _mirror_frame(cv2: Any, frame: Any) -> Any:
    return cv2.flip(frame, 1)


def _load_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required to run HandMouse. Install opencv-python."
        ) from exc

    return cv2


__all__ = ["main"]


if __name__ == "__main__":
    main()
