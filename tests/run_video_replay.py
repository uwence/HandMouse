import argparse
import json
import sys
import time
from typing import Any
from unittest.mock import patch

import cv2

from handmouse.app import _run_loop
from handmouse.camera import Camera
from handmouse.clutch_input import GlobalClutchInput
from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugView
from handmouse.engagement import EngagementConfig, EngagementFSM
from handmouse.gesture_detector import GestureConfig, GestureDetector
from handmouse.grab_scroll_detector import GrabScrollConfig, GrabScrollDetector
from handmouse.hand_tracker import HandTracker
from handmouse.mouse_controller import MouseController
from handmouse.move_mode import MoveModeConfig, MoveModeController
from handmouse.pointer_engine import PointerEngine, PointerEngineConfig
from handmouse.shortcut_controller import ShortcutController
from handmouse.shortcut_detector import ShortcutDetector
from handmouse.interlock import InteractionInterlock


class FakeMouse(MouseController):
    def __init__(self) -> None:
        self.moves: list[tuple[float, float]] = []
        self.clicks = 0
        self.enabled = False

    def set_control_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def move_relative(self, delta: Any) -> None:
        self.moves.append((delta.dx, delta.dy))

    def left_click(self) -> None:
        self.clicks += 1


class FakeShortcutController(ShortcutController):
    def __init__(self) -> None:
        self.enabled = False
        self.scrolled: list[int] = []
        self.executed: list[Any] = []

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def execute(self, action: Any) -> None:
        self.executed.append(action)

    def scroll(self, amount: int) -> None:
        self.scrolled.append(amount)


class FakeCv2:
    def __init__(self, fps: float = 30.0) -> None:
        self.frame_count = 0
        self.fps = fps

    def flip(self, frame: Any, flip_code: int) -> Any:
        return cv2.flip(frame, flip_code)

    def waitKey(self, delay: int) -> int:
        self.frame_count += 1
        # Always engage on frame 5
        if self.frame_count == 5:
            return ord("m")
        return 0

    def imshow(self, name: str, frame: Any) -> None:
        pass

    def destroyAllWindows(self) -> None:
        pass


class MockPerfCounter:
    def __init__(self, fps: float = 30.0) -> None:
        self.current_time = 0.0
        self.fps = fps

    def __call__(self) -> float:
        val = self.current_time
        self.current_time += 1.0 / self.fps
        return val


def main() -> None:
    parser = argparse.ArgumentParser(description="Video Replay Runner")
    parser.add_argument("--video", type=str, required=True, help="Path to input .mp4 video")
    parser.add_argument("--benchmark", type=str, default=None, help="Path to benchmark JSONL to verify against")
    parser.add_argument("--record-telemetry", type=str, default=None, help="Path to dump frame telemetry JSONL")
    args = parser.parse_args()

    config = DEFAULT_CONFIG
    camera = Camera(config.camera)
    camera._backend_name = "VIDEO"
    from handmouse.config import CameraConfig
    from dataclasses import replace
    camera.config = replace(camera.config, index=args.video)
    
    mouse = FakeMouse()
    shortcut = FakeShortcutController()
    clutch_input = GlobalClutchInput(config.clutch.key_name)
    
    screen_w, screen_h = 1920, 1080
    
    mock_cv2 = FakeCv2(fps=30.0)
    mock_perf = MockPerfCounter(fps=30.0)

    try:
        camera.open()
        tracker = HandTracker(num_hands=1)

        pointer = PointerEngine(
            PointerEngineConfig(
                screen_width=screen_w,
                screen_height=screen_h,
                control_region=config.pointer.control_region,
            )
        )
        interlock = InteractionInterlock()
        gesture = GestureDetector(GestureConfig(), interlock=interlock)
        grab_scroll = GrabScrollDetector(GrabScrollConfig(), interlock=interlock)
        shortcut_detector = ShortcutDetector(config.shortcut)
        engagement = EngagementFSM(EngagementConfig())
        move_mode = MoveModeController(MoveModeConfig())
        debug_view = DebugView(config)

        # Mock time.perf_counter
        with patch("time.perf_counter", side_effect=mock_perf):
            _run_loop(
                cv2=mock_cv2,
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
                clutch_status="OK",
                telemetry_file=open(args.record_telemetry, "w", encoding="utf-8") if args.record_telemetry else None,
            )
    except RuntimeError as e:
        # Expected when video ends: "Could not read a frame from the camera."
        if "Could not read a frame" in str(e):
            print("Video playback finished.")
        else:
            raise
    finally:
        camera.release()
        if 'tracker' in locals():
            tracker.close()

    if args.benchmark and args.record_telemetry:
        print(f"Verifying generated telemetry {args.record_telemetry} against benchmark {args.benchmark}...")
        with open(args.record_telemetry, "r", encoding="utf-8") as f_gen, \
             open(args.benchmark, "r", encoding="utf-8") as f_bench:
            gen_lines = f_gen.readlines()
            bench_lines = f_bench.readlines()
            
            assert len(gen_lines) == len(bench_lines), f"Line count mismatch: {len(gen_lines)} != {len(bench_lines)}"
            
            for i, (g_line, b_line) in enumerate(zip(gen_lines, bench_lines)):
                g_data = json.loads(g_line)
                b_data = json.loads(b_line)
                
                # Verify discrete actions
                assert g_data["engagement_active"] == b_data["engagement_active"], f"Frame {i}: engagement mismatch"
                assert g_data["click_triggered"] == b_data["click_triggered"], f"Frame {i}: click mismatch"
                assert g_data["scroll_delta"] == b_data["scroll_delta"], f"Frame {i}: scroll mismatch"
                assert g_data["move_mode"] == b_data["move_mode"], f"Frame {i}: move_mode mismatch"
                
        print("Verification passed!")


if __name__ == "__main__":
    main()
