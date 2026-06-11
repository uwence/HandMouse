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
from handmouse.tracking.observation import HandObservation, Point3, TrackingQuality
from handmouse.tracking.quality_gate import TrackingQualityGate
from handmouse.policy.gesture_policy import GesturePolicy, GestureCandidate, GestureIntent, RiskClass
from handmouse.actions.windows_backend import ActionRouter
from handmouse.shortcut_detector import ShortcutAction
from handmouse.telemetry.schema import (
    build_frame_sample,
    build_gesture_candidate,
    build_gesture_decision,
)



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
        running_mode_str = getattr(config.camera, "running_mode", "video")
        from mediapipe.tasks.python import vision
        tracker_mode = (
            vision.RunningMode.LIVE_STREAM
            if running_mode_str == "live_stream"
            else vision.RunningMode.VIDEO
        )
        tracker = HandTracker(running_mode=tracker_mode, num_hands=1)

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
                pinch_close_ratio=config.gesture_config.pinch_close_ratio,
                pinch_open_ratio=config.gesture_config.pinch_open_ratio,
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
        quality_gate = TrackingQualityGate()
        policy = GesturePolicy(
            config.policy.high_risk_cooldown_ms,
            explicit_confirm_required=config.policy.explicit_confirm_required,
        )
        action_router = ActionRouter(mouse, shortcut)
        
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

        if args.record_telemetry:
            import os
            from handmouse.telemetry.writer import TelemetryWriter
            import handmouse.telemetry.writer as tel_writer
            filepath = args.record_telemetry
            if tel_writer._global_writer is not None:
                tel_writer._global_writer.close()
            tel_writer._global_writer = TelemetryWriter(log_file=filepath, enabled=True)
            
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
                    interlock=interlock,
                    clutch_input=clutch_input,
                    move_mode=move_mode,
                    clutch_status=clutch_status,
                    telemetry_file=None,
                    camera_reader=camera_reader,
                    inference_worker=inference_worker,
                    alt_tab_detector=alt_tab_detector,
                    osd=osd,
                    quality_gate=quality_gate,
                    policy=policy,
                    action_router=action_router,
                )
            except Exception as e:
                print(f"Error in HandMouse loop: {e}")
            finally:
                try:
                    from handmouse.tray import stop_tray_icon
                    stop_tray_icon()
                except Exception:
                    pass
                try:
                    from handmouse.telemetry.writer import close_telemetry
                    close_telemetry()
                except Exception:
                    pass
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
    interlock: InteractionInterlock,
    clutch_input: Any | None = None,
    move_mode: Any | None = None,
    clutch_status: str | None = None,
    telemetry_file: Any | None = None,
    camera_reader: CameraReader | None = None,
    inference_worker: InferenceWorker | None = None,
    alt_tab_detector: AltTabDetector | None = None,
    osd: Any | None = None,
    quality_gate: TrackingQualityGate | None = None,
    policy: GesturePolicy | None = None,
    action_router: ActionRouter | None = None,
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
    last_task_view_ms = 0

    import handmouse.config as conf

    while True:
        global SHOULD_EXIT
        if SHOULD_EXIT:
            break

        decisions: list[Any] = []
        intents: list[GestureIntent] = []
        dispatches: list[Any] = []
        candidates: list[GestureCandidate] = []

        config = conf.ACTIVE_CONFIG
        if config is not last_applied_config:
            last_applied_config = _apply_runtime_settings(
                camera=camera,
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
        
        # Update calibration state if active
        try:
            from handmouse.ui.calibration_state import STATE as calibration_state
            if calibration_state.active and hand_result and hand_result.landmarks and len(hand_result.landmarks) >= 21:
                from math import hypot
                lm = hand_result.landmarks
                palm_span = hypot(lm[5].x - lm[17].x, lm[5].y - lm[17].y)
                if palm_span == 0:
                    palm_span = 1.0
                left_ratio = hypot(lm[4].x - lm[8].x, lm[4].y - lm[8].y) / palm_span
                calibration_state.update(left_ratio, palm_span)
        except Exception:
            pass
            
        hand_missing = not hand_result or not hand_result.landmarks

        clutch_snapshot = _clutch_snapshot(clutch_input)
            
        landmarks = hand_result.landmarks if hand_result else None
        move_pose = _is_move_pose(landmarks)
        
        palm_visible = _is_palm_open(landmarks)
        vsign_visible = _is_vsign_open(landmarks)
        
        if clutch_snapshot.clutch_down and move_pose:
            palm_visible = True
            
        if palm_visible:
            if palm_visible_start_ms is None:
                palm_visible_start_ms = now_ms
            palm_hold_ms = now_ms - palm_visible_start_ms
            if clutch_snapshot.clutch_down and move_pose:
                palm_hold_ms = 9999
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
        if quality_gate is None:
            quality_gate = TrackingQualityGate()
        if policy is None:
            policy = GesturePolicy(
                config.policy.high_risk_cooldown_ms,
                explicit_confirm_required=config.policy.explicit_confirm_required,
            )
        if action_router is None:
            action_router = ActionRouter(mouse, shortcut)

        obs = None
        if hand_result and hand_result.landmarks:
            raw_landmarks = getattr(hand_result, "raw_landmarks", None)
            pts = []
            for idx, lm in enumerate(hand_result.landmarks):
                z = 0.0
                if raw_landmarks is not None and idx < len(raw_landmarks):
                    z = float(getattr(raw_landmarks[idx], "z", 0.0))
                pts.append(Point3(x=lm.x, y=lm.y, z=z))
            obs = HandObservation(
                frame_id=0,
                ts_ms=now_ms,
                image_landmarks=pts,
                world_landmarks=hand_result.world_landmarks,
                handedness_label=getattr(hand_result, "handedness_label", None),
                handedness_score=getattr(hand_result, "handedness_confidence", None),
                raw_result=hand_result,
                stale_ms=frame_age_ms,
                camera_space="mirrored"
            )

        frame_shape = getattr(frame, "shape", None)
        if frame_shape is not None and len(frame_shape) >= 2:
            frame_h, frame_w = frame_shape[:2]
        else:
            frame_w = getattr(config.camera, "width", 640)
            frame_h = getattr(config.camera, "height", 480)
        quality = quality_gate.update(obs, frame_w, frame_h)

        is_dragging = False
        if getattr(gesture, "_left_state", GestureState.PINCH_OPEN) == GestureState.PINCH_HOLD or \
           getattr(gesture, "_right_state", GestureState.PINCH_OPEN) == GestureState.PINCH_HOLD:
            is_dragging = True
            
        effective_move_active = (is_active and move_mode_result.movement_enabled) or is_dragging

        try:
            if effective_move_active:
                delta = pointer.update(hand_result, now_ms)
                if delta is not None and (delta.dx != 0 or delta.dy != 0):
                    mouse.move_relative(delta)
                    dx = delta.dx
                    dy = delta.dy
            elif is_active and not clutch_snapshot.clutch_down:
                pointer.reset()
                
            if is_active:
                if alt_tab_detector is not None:
                    candidates.extend(alt_tab_detector.update(hand_result.landmarks, now_ms))

                candidates.extend(grab_scroll.update(obs, now_ms))
                candidates.extend(gesture.update(obs, now_ms))
                
                index_tip = hand_result.index_tip if hand_result else None
                candidates.extend(shortcut_detector.update(obs, now_ms, index_tip, palm_open=palm_visible))
            else:
                if alt_tab_detector is not None:
                    alt_tab_detector.reset()
                gesture.reset()
                grab_scroll.reset()
                shortcut_detector.reset()
                pointer.reset()

            if candidates:
                decisions = policy.evaluate(obs, quality, candidates, {"now_ms": now_ms})
                intents = [
                    GestureIntent(
                        action=decision.action,
                        risk=decision.risk,
                        detector=decision.detector,
                        committed=True,
                        payload=decision.payload,
                    )
                    for decision in decisions
                    if decision.committed
                ]
                
                try:
                    from handmouse.telemetry.writer import log_event
                    for decision in decisions:
                        log_event(
                            "gesture_decision",
                            build_gesture_decision(
                                ts_ms=now_ms,
                                action=decision.action,
                                risk=decision.risk.value if hasattr(decision.risk, "value") else decision.risk,
                                detector=decision.detector,
                                committed=decision.committed,
                                blocked_by=decision.payload.get("blocked_by"),
                                quality_score=quality.score,
                                quality_reasons=quality.reasons,
                            ),
                        )
                except Exception:
                    pass

                dispatches = action_router.dispatch(intents, {})
                
                for dispatch in dispatches:
                    if dispatch.action == "task_view" and dispatch.executed:
                        last_task_view_ms = now_ms


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
            clutch_down=clutch_snapshot.clutch_down,
            clutch_status=clutch_status,
            move_mode=move_mode_result.state.name,
            candidates=candidates,
            dispatches=dispatches,
            move_pose=move_mode_result.move_pose,
        )

        debug_frame = debug_view.draw(
            frame,
            raw_hand_result,
            __import__('types').SimpleNamespace(
                state=getattr(gesture, "_left_state", GestureState.PINCH_OPEN), 
                pinch_distance=getattr(gesture, "last_distance", 1.0)
            ),
            is_active,
            telemetry,
        )

        cv2.imshow(WINDOW_NAME, debug_frame)

        try:
            from handmouse.telemetry.writer import log_event
            log_event(
                "frame_sample",
                build_frame_sample(
                    ts_ms=now_ms,
                    frame_capture_time=frame_capture_time,
                    frame_age_ms=frame_age_ms,
                    pointer_dx=dx,
                    pointer_dy=dy,
                    engagement_active=is_active,
                    clutch_down=clutch_snapshot.clutch_down,
                    move_mode=move_mode_result.state.name,
                    hand_found=bool(hand_result and hand_result.landmarks),
                    landmarks=[[lm.x, lm.y, lm.z] for lm in obs.image_landmarks] if obs else [],
                    world_landmarks=[[lm.x, lm.y, lm.z] for lm in hand_result.world_landmarks] if (hand_result and hand_result.world_landmarks) else None,
                    quality_score=quality.score,
                    quality_reasons=quality.reasons,
                ),
            )
            
            for cand in candidates:
                log_event(
                    "gesture_candidate",
                    build_gesture_candidate(
                        ts_ms=now_ms,
                        detector=cand.detector,
                        gesture=cand.gesture,
                        phase=cand.phase,
                        confidence=cand.confidence,
                    ),
                )
        except Exception:
            pass

def _apply_runtime_settings(
    *,
    camera: Camera,
    pointer: PointerEngine,
    gesture: GestureDetector,
    grab_scroll: GrabScrollDetector,
    shortcut_detector: ShortcutDetector,
    debug_view: DebugView,
    config: AppConfig,
    last_applied_config: AppConfig | None,
    osd: Any | None = None,
) -> AppConfig:
    # Update camera config
    if hasattr(camera, "config"):
        camera.config = config.camera
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
            pinch_close_ratio=config.gesture_config.pinch_close_ratio,
            pinch_open_ratio=config.gesture_config.pinch_open_ratio,
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
    if (palm_width / palm_height) < 0.30:
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
        # Pass the metrics to some global debug state so we can render them on OSD
        debug_metrics = f"v1=({v1_x:.2f},{v1_y:.2f}) v2=({v2_x:.2f},{v2_y:.2f}) c={cross:.3f} L={is_left}"
        coordinate_mapper.DEBUG_CROSS = debug_metrics

        if is_left:
            if cross >= 0:  # Back of left hand
                return False
        else:
            if cross <= 0:  # Back of right hand
                return False

    # Without handedness_label we cannot distinguish palm from back-of-hand;
    # fall through to the sideways check only. Caller should treat falsy as
    # "unverified" rather than assuming palm-facing.
    return handedness_label is not None


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
        if mcp_d > 0 and tip_d / mcp_d > 1.0:
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
