from handmouse.config import ControlRegion, PointerConfig
from handmouse.pointer_mapper import FramePoint, PointerMapper, ScreenPoint


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


def test_none_resets_smoothing_state() -> None:
    mapper = make_mapper(smoothing=0.25)

    assert mapper.update(FramePoint(0.25, 0.25)) == ScreenPoint(0, 0)
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(25, 25)
    assert mapper.update(None) is None
    assert mapper.update(FramePoint(0.75, 0.75)) == ScreenPoint(100, 100)
