from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

from handmouse.config import DEFAULT_CONFIG
from handmouse.debug_view import DebugTelemetry, DebugView
from handmouse.gesture_detector import GestureState
from handmouse.types import FramePoint, ScreenPoint


def test_debug_view_draw(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cv2 = MagicMock()
    # Mock some opencv properties and drawing methods
    mock_cv2.LINE_AA = 16
    mock_cv2.FONT_HERSHEY_SIMPLEX = 0
    
    # Mock load_cv2
    monkeypatch.setattr("handmouse.debug_view._load_cv2", lambda: mock_cv2)
    monkeypatch.setattr(sys, "modules", {**sys.modules, "cv2": mock_cv2})

    config = DEFAULT_CONFIG.__class__(
        camera=DEFAULT_CONFIG.camera,
        pointer=DEFAULT_CONFIG.pointer,
        shortcut=DEFAULT_CONFIG.shortcut,
        clutch=DEFAULT_CONFIG.clutch,
        schema_version=DEFAULT_CONFIG.schema_version,
        policy=DEFAULT_CONFIG.policy,
        gesture_switches=DEFAULT_CONFIG.gesture_switches,
        gesture_config=DEFAULT_CONFIG.gesture_config,
        grab_scroll_config=DEFAULT_CONFIG.grab_scroll_config,
        view=DEFAULT_CONFIG.view.__class__(render_mirrored=False),
        show_osd=DEFAULT_CONFIG.show_osd,
    )
    view = DebugView(config)

    # Mock frame with shape and copy method
    frame = SimpleNamespace(shape=(480, 640, 3))
    frame.copy = lambda: frame

    # Test with no hand, no gesture, no telemetry
    res = view.draw(frame, None, None, control_enabled=False, telemetry=None)
    assert res == frame
    assert mock_cv2.rectangle.call_count > 0

    # Reset mock call counts
    mock_cv2.reset_mock()

    # Test with hand, gesture and telemetry
    landmarks = [FramePoint(0.5, 0.5) for _ in range(21)]
    hand_result = SimpleNamespace(
        landmarks=landmarks,
        thumb_tip=FramePoint(0.4, 0.4),
        index_tip=FramePoint(0.6, 0.6),
        raw_landmarks=None,
        handedness_label="Left",
        handedness_confidence=0.95,
    )
    
    gesture_result = None

    pointer = SimpleNamespace(
        state=SimpleNamespace(name="ACTIVE"),
        last_velocity=1.5,
        last_gain=1.2,
        last_depth_factor=1.0,
        last_hand_scale=0.15,
        config=SimpleNamespace(control_region=DEFAULT_CONFIG.pointer.control_region),
    )

    engagement = SimpleNamespace(
        state=SimpleNamespace(name="ACTIVE"),
        reason="palm_hold",
        is_active=True,
    )

    grab_scroll = SimpleNamespace(
        state=SimpleNamespace(name="GRABBING"),
        scroll_delta=10,
        is_grab_pose=True,
        active=True,
    )

    telemetry = DebugTelemetry(
        fps=60.0,
        frame_age_ms=12,
        backend_name="CAP_DSHOW",
        pointer=pointer,
        engagement=engagement,
        grab_scroll=grab_scroll,
        clutch_down=True,
        clutch_status="OK",
        move_mode="ACTIVE",
        move_pose=True,
    )

    res = view.draw(frame, hand_result, gesture_result, control_enabled=True, telemetry=telemetry)
    assert res == frame
    
    # Assert drawing methods were called for landmarks and text overlays
    assert mock_cv2.circle.call_count > 0
    assert mock_cv2.line.call_count > 0
    assert mock_cv2.putText.call_count > 0


def test_debug_view_flips_frame_when_render_mirrored_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_cv2 = MagicMock()
    mock_cv2.LINE_AA = 16
    mock_cv2.FONT_HERSHEY_SIMPLEX = 0
    flipped_frame = SimpleNamespace(shape=(480, 640, 3))
    flipped_frame.copy = lambda: flipped_frame
    mock_cv2.flip.side_effect = lambda frame, code: flipped_frame

    monkeypatch.setattr("handmouse.debug_view._load_cv2", lambda: mock_cv2)
    monkeypatch.setattr(sys, "modules", {**sys.modules, "cv2": mock_cv2})

    config = DEFAULT_CONFIG.__class__(
        camera=DEFAULT_CONFIG.camera,
        pointer=DEFAULT_CONFIG.pointer,
        shortcut=DEFAULT_CONFIG.shortcut,
        clutch=DEFAULT_CONFIG.clutch,
        schema_version=DEFAULT_CONFIG.schema_version,
        policy=DEFAULT_CONFIG.policy,
        gesture_switches=DEFAULT_CONFIG.gesture_switches,
        gesture_config=DEFAULT_CONFIG.gesture_config,
        grab_scroll_config=DEFAULT_CONFIG.grab_scroll_config,
        view=DEFAULT_CONFIG.view.__class__(render_mirrored=True),
        show_osd=DEFAULT_CONFIG.show_osd,
    )
    view = DebugView(config)
    frame = SimpleNamespace(shape=(480, 640, 3))
    frame.copy = lambda: frame

    result = view.draw(frame, None, None, control_enabled=False, telemetry=None)

    assert result == flipped_frame
    mock_cv2.flip.assert_called_once_with(frame, 1)
