from __future__ import annotations

import sys
from unittest.mock import MagicMock
import pytest
from math import hypot

from handmouse.tracking.observation import HandObservation, Point3
from handmouse.tracking.quality_gate import TrackingQualityGate
from handmouse.policy.gesture_policy import GesturePolicy
from handmouse.gesture_detector import GestureDetector, GestureConfig
from handmouse.grab_scroll_detector import GrabScrollDetector, GrabScrollConfig
from handmouse.alt_tab_detector import AltTabDetector
from handmouse.actions.windows_backend import ActionRouter
from handmouse.interlock import InteractionInterlock
from handmouse.types import FramePoint


# Helper to build a default open hand
def build_open_hand_landmarks() -> list[list[float]]:
    points = [[0.0, 0.0] for _ in range(21)]
    # Wrist (0)
    points[0] = [0.5, 0.9]
    # Thumb
    points[2] = [0.35, 0.75]
    points[3] = [0.28, 0.6]
    points[4] = [0.2, 0.4]
    # Index
    points[5] = [0.4, 0.6]
    points[6] = [0.4, 0.4]
    points[8] = [0.4, 0.2]
    # Middle
    points[9] = [0.48, 0.6]
    points[10] = [0.48, 0.4]
    points[12] = [0.48, 0.18]
    # Ring
    points[13] = [0.55, 0.6]
    points[14] = [0.55, 0.4]
    points[16] = [0.55, 0.2]
    # Pinky
    points[17] = [0.62, 0.6]
    points[18] = [0.62, 0.4]
    points[20] = [0.62, 0.25]
    return points


# Helper to build a pinch pose
def build_pinch_landmarks() -> list[list[float]]:
    points = build_open_hand_landmarks()
    # Pinch: Thumb and Index Tips are touching
    points[4] = [0.4, 0.3]
    points[8] = [0.4, 0.3]
    return points


# Helper to build a grab (fist) pose
def build_grab_landmarks(y_offset: float = 0.0) -> list[list[float]]:
    points = [[0.0, 0.0] for _ in range(21)]
    # Wrist (0)
    points[0] = [0.50, 0.80 + y_offset]
    # MCPs
    points[5] = [0.40, 0.56 + y_offset]
    points[9] = [0.50, 0.58 + y_offset]
    points[13] = [0.60, 0.60 + y_offset]
    points[17] = [0.68, 0.62 + y_offset]
    # Curled tips
    points[4] = [0.36, 0.55 + y_offset]
    points[8] = [0.45, 0.50 + y_offset]
    points[12] = [0.52, 0.49 + y_offset]
    points[16] = [0.57, 0.52 + y_offset]
    points[20] = [0.62, 0.58 + y_offset]
    return points


# Helper to build Alt-Tab (3 fingers extended, Pinky curled)
def build_alt_tab_landmarks(x_offset: float = 0.0) -> list[list[float]]:
    points = [[0.0, 0.0] for _ in range(21)]
    # Wrist (0)
    points[0] = [0.5 + x_offset, 0.9]
    # MCPs to satisfy palm span check in quality gate
    points[5] = [0.4 + x_offset, 0.6]
    points[9] = [0.48 + x_offset, 0.6]
    points[13] = [0.55 + x_offset, 0.6]
    points[17] = [0.62 + x_offset, 0.6]
    # Pips
    points[6] = [0.5 + x_offset, 0.4]
    points[10] = [0.6 + x_offset, 0.4]
    points[14] = [0.7 + x_offset, 0.4]
    points[18] = [0.8 + x_offset, 0.6]
    # Tips: Index (8), Middle (12), Ring (16) extended, Pinky (20) curled
    points[8] = [0.5 + x_offset, 0.2]
    points[12] = [0.6 + x_offset, 0.2]
    points[16] = [0.7 + x_offset, 0.2]
    points[20] = [0.8 + x_offset, 0.7]
    return points


def run_pipeline_simulation(landmarks_series) -> list[str]:
    interlock = InteractionInterlock()
    gesture = GestureDetector(GestureConfig(pinch_close_ratio=0.5, pinch_open_ratio=0.7), interlock=interlock)
    grab_scroll = GrabScrollDetector(
        GrabScrollConfig(
            hold_ms=100,
            dead_zone=0.01,
            scroll_sensitivity=200.0,
            only_active_when_draging=True
        ),
        interlock=interlock
    )
    alt_tab = AltTabDetector(arming_time_ms=100, nav_threshold=0.08, cooldown_ms=100)
    quality_gate = TrackingQualityGate()
    policy = GesturePolicy()

    mock_mouse = MagicMock()
    mock_shortcut = MagicMock()
    router = ActionRouter(mock_mouse, mock_shortcut)

    dispatched_actions = []

    # Run loop
    for idx, lms in enumerate(landmarks_series):
        now_ms = 1000 + idx * 50  # 50ms interval (20fps)

        if lms is not None:
            pts = [Point3(x=lm[0], y=lm[1], z=0.0) for lm in lms]
            obs = HandObservation(
                frame_id=idx,
                ts_ms=now_ms,
                image_landmarks=pts,
                world_landmarks=pts,
                handedness_label="Right",
                handedness_score=0.99,
                raw_result=None,
                stale_ms=0,
                camera_space="mirrored"
            )
        else:
            obs = None

        quality = quality_gate.update(obs, 1920, 1080)

        candidates = []
        if obs is not None:
            candidates.extend(gesture.update(obs, now_ms))
            candidates.extend(grab_scroll.update(obs, now_ms))
            
            lms_points = [FramePoint(lm[0], lm[1]) for lm in lms]
            candidates.extend(alt_tab.update(lms_points, now_ms))

        intents = policy.evaluate(obs, quality, candidates, {})
        dispatches = router.dispatch(intents, {})

        for d in dispatches:
            if d.executed:
                dispatched_actions.append(d.action)

    return dispatched_actions


def test_regression_click_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scenario: Open Hand -> Pinch -> Holds -> Release
    monkeypatch.setattr("handmouse.actions.windows_backend.pyautogui", MagicMock())
    
    series = []
    # 3 frames open
    for _ in range(3):
        series.append(build_open_hand_landmarks())
    # 4 frames pinch
    for _ in range(4):
        series.append(build_pinch_landmarks())
    # 3 frames open
    for _ in range(3):
        series.append(build_open_hand_landmarks())

    actions = run_pipeline_simulation(series)
    
    # Should click_left at release, or drag_hold at pressed
    assert "click_left" in actions
    assert "drag_hold" in actions
    assert "drag_release" in actions


def test_regression_scroll_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scenario: Open Hand -> Grab -> Holds while moving up -> Releases
    monkeypatch.setattr("handmouse.actions.windows_backend.pyautogui", MagicMock())
    
    series = []
    # 2 frames open
    for _ in range(2):
        series.append(build_open_hand_landmarks())
    # 2 frames static grab to arm
    for _ in range(2):
        series.append(build_grab_landmarks())
    # 3 frames grab moving up
    for i in range(3):
        series.append(build_grab_landmarks(y_offset=-0.05 * (i + 1)))
    # 2 frames open to release
    for _ in range(2):
        series.append(build_open_hand_landmarks())

    actions = run_pipeline_simulation(series)
    assert "scroll" in actions


def test_regression_alt_tab_and_navigation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Scenario: Open Hand -> Alt Tab Pose -> Shift hand left -> Release
    monkeypatch.setattr("handmouse.actions.windows_backend.pyautogui", MagicMock())
    
    series = []
    # Open
    series.append(build_open_hand_landmarks())
    # Alt Tab Pose held to arm (arming time is 100ms, frame step is 50ms)
    series.append(build_alt_tab_landmarks(x_offset=0.0))
    series.append(build_alt_tab_landmarks(x_offset=0.0))
    series.append(build_alt_tab_landmarks(x_offset=0.0))
    # Shift hand left to navigate
    series.append(build_alt_tab_landmarks(x_offset=-0.15))
    series.append(build_alt_tab_landmarks(x_offset=-0.15))
    # Release to commit
    series.append(build_open_hand_landmarks())

    actions = run_pipeline_simulation(series)
    
    assert "task_view" in actions
    assert "nav_left" in actions
    assert "task_view_commit" in actions
