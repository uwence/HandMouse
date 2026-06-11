from __future__ import annotations

from handmouse.config import ControlRegion
from handmouse.hand_tracker import HandTrackingResult
from handmouse.pointer_engine import (
    PointerEngine,
    PointerEngineConfig,
    PointerEngineState,
)
from handmouse.types import FramePoint, ScreenDelta


def make_engine(
    *,
    screen_width: int = 100,
    screen_height: int = 100,
    control_region: ControlRegion = ControlRegion(left=0.0, top=0.0, right=1.0, bottom=1.0),
    z_scale_reference: float | None = 1.0,
    missing_frames_to_idle: int = 4,
    pixel_per_palm_width: float | None = None,
) -> PointerEngine:
    return PointerEngine(
        PointerEngineConfig(
            screen_width=screen_width,
            screen_height=screen_height,
            control_region=control_region,
            z_scale_reference=z_scale_reference,
            missing_frames_to_idle=missing_frames_to_idle,
            pixel_per_palm_width=pixel_per_palm_width,
        )
    )


def make_landmarks(
    *,
    scale: float = 0.2,
    index_tip: FramePoint = FramePoint(0.0, 0.0),
) -> list[FramePoint]:
    landmarks = [FramePoint(0.0, 0.0) for _ in range(21)]
    landmarks[0] = FramePoint(0.0, 0.0)  # wrist
    landmarks[5] = FramePoint(scale, 0.0)  # index_mcp
    landmarks[9] = FramePoint(0.0, scale)  # middle_mcp
    landmarks[17] = FramePoint(0.0, scale)  # pinky_mcp
    landmarks[8] = index_tip
    return landmarks


def make_hand_result(
    *,
    scale: float = 0.2,
    index_tip: FramePoint = FramePoint(0.0, 0.0),
) -> HandTrackingResult:
    landmarks = make_landmarks(scale=scale, index_tip=index_tip)
    return HandTrackingResult(
        landmarks=landmarks,
        thumb_tip=FramePoint(index_tip.x, index_tip.y),
        index_tip=index_tip,
        raw_landmarks=None,
        world_landmarks=None,
        handedness_label=None,
        handedness_confidence=None,
    )


def test_no_hand_returns_none() -> None:
    engine = make_engine()

    assert engine.update(None, now_ms=0) is None
    assert engine.update(
        HandTrackingResult(
            landmarks=[],
            thumb_tip=None,
            index_tip=None,
            raw_landmarks=None,
            world_landmarks=None,
            handedness_label=None,
            handedness_confidence=None,
        ),
        now_ms=16,
    ) is None


def test_first_call_returns_none_anchors() -> None:
    engine = make_engine()

    assert engine.update(make_hand_result(index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None
    assert engine.state is PointerEngineState.ACTIVE
    assert engine.last_velocity is None


def test_jitter_below_threshold_outputs_zero_delta() -> None:
    engine = make_engine()

    assert engine.update(make_hand_result(index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    delta = engine.update(make_hand_result(index_tip=FramePoint(0.01, 0.0)), now_ms=100)

    assert delta == ScreenDelta(0, 0)
    assert engine.last_gain == 0.0
    assert engine.state is PointerEngineState.ACTIVE


def test_small_motion_above_velocity_threshold_is_not_blocked_by_displacement() -> None:
    engine = make_engine(screen_width=100, screen_height=100, z_scale_reference=0.2)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    delta = engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.05, 0.0)), now_ms=100)

    assert delta is not None
    assert delta.dx > 0
    assert engine.last_gain is not None
    assert 0.0 < engine.last_gain < 1.0


def test_mid_speed_approximate_one_to_one() -> None:
    engine = make_engine(screen_width=100, screen_height=100, z_scale_reference=0.2)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    delta = engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(1.0, 0.0)), now_ms=1000)

    assert delta == ScreenDelta(100, 0)
    assert engine.last_gain == 1.0
    assert engine.last_depth_factor == 1.0


def test_high_speed_applies_gain() -> None:
    engine = make_engine(screen_width=100, screen_height=100)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    delta = engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(1.0, 0.0)), now_ms=333)

    assert delta is not None
    assert delta.dx > 100
    assert engine.last_gain is not None and engine.last_gain > 1.0


def test_depth_compensation_clamps_to_z_min() -> None:
    engine = make_engine(z_scale_reference=0.2)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    assert engine.update(make_hand_result(scale=0.4, index_tip=FramePoint(1.0, 0.0)), now_ms=1000) == ScreenDelta(
        70,
        0,
    )
    assert engine.last_depth_factor == 0.7


def test_depth_compensation_clamps_to_z_max() -> None:
    engine = make_engine(z_scale_reference=0.2)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    assert engine.update(make_hand_result(scale=0.1, index_tip=FramePoint(1.0, 0.0)), now_ms=1000) == ScreenDelta(
        125,
        0,
    )
    assert engine.last_depth_factor == 1.25


def test_hand_lost_returns_none_after_missing_frames() -> None:
    engine = make_engine(missing_frames_to_idle=4)

    assert engine.update(make_hand_result(index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None

    assert engine.update(None, now_ms=16) is None
    assert engine.state is PointerEngineState.COOLDOWN
    assert engine.update(None, now_ms=32) is None
    assert engine.update(None, now_ms=48) is None
    assert engine.update(None, now_ms=64) is None
    assert engine.state is PointerEngineState.IDLE


def test_reset_clears_state() -> None:
    engine = make_engine(z_scale_reference=0.2)

    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.0, 0.0)), now_ms=0) is None
    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(1.0, 0.0)), now_ms=1000) == ScreenDelta(100, 0)

    engine.reset()

    assert engine.state is PointerEngineState.IDLE
    assert engine.last_gain is None
    assert engine.last_velocity is None
    assert engine.update(make_hand_result(scale=0.2, index_tip=FramePoint(0.5, 0.0)), now_ms=2000) is None
