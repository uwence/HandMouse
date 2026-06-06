from handmouse.config import DEFAULT_CONFIG, ControlRegion, PointerConfig
from handmouse.pointer_mapper import FramePoint, PointerMapper, ScreenPoint
from handmouse.pointer_mapper import RelativePointerMapper, ScreenDelta


def make_mapper(
    *,
    smoothing: float = 0.5,
    dead_zone_px: float = 0.0,
    screen_width: int = 101,
    screen_height: int = 101,
    control_region: ControlRegion = ControlRegion(left=0.25, top=0.25, right=0.75, bottom=0.75),
) -> PointerMapper:
    return PointerMapper(
        screen_width=screen_width,
        screen_height=screen_height,
        config=PointerConfig(
            smoothing=smoothing,
            dead_zone_px=dead_zone_px,
            control_region=control_region,
        ),
    )


def make_relative_mapper(
    *,
    dead_zone_px: float = 0.0,
    relative_sensitivity: float = 1.0,
    screen_width: int = 100,
    screen_height: int = 100,
    control_region: ControlRegion = ControlRegion(left=0.25, top=0.25, right=0.75, bottom=0.75),
) -> RelativePointerMapper:
    return RelativePointerMapper(
        screen_width=screen_width,
        screen_height=screen_height,
        config=PointerConfig(
            smoothing=0.5,
            dead_zone_px=dead_zone_px,
            control_region=control_region,
            relative_sensitivity=relative_sensitivity,
        ),
    )


def test_center_of_control_region_maps_to_center_of_screen() -> None:
    mapper = make_mapper(smoothing=0.5)

    assert mapper.update(FramePoint(0.5, 0.5)) == ScreenPoint(50, 50)


def test_points_outside_region_clamp_to_edges() -> None:
    mapper = make_mapper(smoothing=0.5)

    assert mapper.update(FramePoint(-1.0, 2.0)) == ScreenPoint(0, 100)


def test_first_point_does_not_lag() -> None:
    mapper = make_mapper(smoothing=0.1)

    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(100, 100)


def test_second_point_is_smoothed() -> None:
    mapper = make_mapper(smoothing=0.25)

    assert mapper.update(FramePoint(0.25, 0.25)) == ScreenPoint(0, 0)
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(25, 25)


def test_smoothing_above_one_does_not_overshoot_screen_bounds() -> None:
    mapper = make_mapper(smoothing=2.0)

    assert mapper.update(FramePoint(0.25, 0.25)) == ScreenPoint(0, 0)
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(100, 100)


def test_none_resets_smoothing_state() -> None:
    mapper = make_mapper(smoothing=0.25)

    assert mapper.update(FramePoint(0.25, 0.25)) == ScreenPoint(0, 0)
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(25, 25)
    assert mapper.update(None) is None
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(100, 100)


def test_dead_zone_suppresses_movement_within_threshold() -> None:
    mapper = make_mapper(smoothing=1.0, dead_zone_px=5.0)

    assert mapper.update(FramePoint(0.5, 0.5)) == ScreenPoint(50, 50)
    assert mapper.update(FramePoint(0.51, 0.51)) == ScreenPoint(50, 50)


def test_dead_zone_allows_movement_beyond_threshold() -> None:
    mapper = make_mapper(smoothing=1.0, dead_zone_px=5.0)

    assert mapper.update(FramePoint(0.5, 0.5)) == ScreenPoint(50, 50)
    assert mapper.update(FramePoint(0.6, 0.6)) == ScreenPoint(70, 70)


def test_dead_zone_reset_clears_previous_output() -> None:
    mapper = make_mapper(smoothing=1.0, dead_zone_px=5.0)

    assert mapper.update(FramePoint(0.5, 0.5)) == ScreenPoint(50, 50)
    assert mapper.update(None) is None
    assert mapper.update(FramePoint(0.51, 0.51)) == ScreenPoint(52, 52)


def test_default_control_region_is_inset_from_frame_edges() -> None:
    region = DEFAULT_CONFIG.pointer.control_region

    assert 0.0 < region.left < region.right < 1.0
    assert 0.0 < region.top < region.bottom < 1.0


def test_last_frame_point_tracks_smoothed_target_inside_control_region() -> None:
    mapper = make_mapper(
        smoothing=0.5,
        control_region=ControlRegion(left=0.1, top=0.2, right=0.9, bottom=0.8),
    )

    mapper.update(FramePoint(0.1, 0.2))
    assert mapper.last_frame_point == FramePoint(0.1, 0.2)

    mapper.update(FramePoint(0.9, 0.8))
    assert mapper.last_frame_point == FramePoint(0.5, 0.5)


def test_relative_mapper_first_point_anchors_without_moving() -> None:
    mapper = make_relative_mapper()

    assert mapper.update(FramePoint(0.5, 0.5)) is None
    assert mapper.last_frame_point == FramePoint(0.5, 0.5)


def test_relative_mapper_outputs_directional_delta() -> None:
    mapper = make_relative_mapper()

    assert mapper.update(FramePoint(0.5, 0.5)) is None
    assert mapper.update(FramePoint(0.55, 0.45)) == ScreenDelta(10, -10)


def test_relative_mapper_applies_sensitivity() -> None:
    mapper = make_relative_mapper(relative_sensitivity=2.0)

    assert mapper.update(FramePoint(0.5, 0.5)) is None
    assert mapper.update(FramePoint(0.55, 0.5)) == ScreenDelta(20, 0)


def test_relative_mapper_dead_zone_suppresses_jitter() -> None:
    mapper = make_relative_mapper(dead_zone_px=12.0)

    assert mapper.update(FramePoint(0.5, 0.5)) is None
    assert mapper.update(FramePoint(0.52, 0.5)) is None


def test_relative_mapper_reset_prevents_reentry_jump() -> None:
    mapper = make_relative_mapper()

    assert mapper.update(FramePoint(0.25, 0.25)) is None
    assert mapper.update(None) is None
    assert mapper.update(FramePoint(0.75, 0.75)) is None
