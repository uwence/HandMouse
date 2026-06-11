from handmouse.config.schema import (
    AppConfig, CameraConfig, PointerConfig, ControlRegion,
    ShortcutConfig, ClutchConfig, GestureSwitches,
    ExtendedGestureConfig, ExtendedGrabScrollConfig, ViewConfig,
    SUPPORTED_BACKENDS
)

# Shared common base config
_base_camera = CameraConfig(
    width=640,
    height=480,
    index=0,
    backend_preference=SUPPORTED_BACKENDS,
    buffer_size=1,
    fps_target=60,
    input_is_mirrored=False,
)
_base_view = ViewConfig(render_mirrored=True)
_base_clutch = ClutchConfig(key_name="ctrl_r")
_base_switches = GestureSwitches()

DEFAULT_PROFILE = AppConfig(
    camera=_base_camera,
    view=_base_view,
    pointer=PointerConfig(
        control_region=ControlRegion(left=0.12, top=0.10, right=0.88, bottom=0.90),
        g_hi=3.0,
    ),
    shortcut=ShortcutConfig(
        min_distance=0.18,
        max_duration_ms=900,
        cooldown_ms=700,
        axis_ratio=1.4,
    ),
    clutch=_base_clutch,
    gesture_switches=_base_switches,
    gesture_config=ExtendedGestureConfig(pinch_close_ratio=0.5, pinch_open_ratio=0.7),
    grab_scroll_config=ExtendedGrabScrollConfig(scroll_sensitivity=180.0),
)

AGGRESSIVE_PROFILE = AppConfig(
    camera=_base_camera,
    view=_base_view,
    pointer=PointerConfig(
        control_region=ControlRegion(left=0.15, top=0.15, right=0.85, bottom=0.85),
        g_hi=4.5,
    ),
    shortcut=ShortcutConfig(
        min_distance=0.15,
        max_duration_ms=1200,
        cooldown_ms=500,
        axis_ratio=1.2,
    ),
    clutch=_base_clutch,
    gesture_switches=_base_switches,
    gesture_config=ExtendedGestureConfig(pinch_close_ratio=0.6, pinch_open_ratio=0.8),
    grab_scroll_config=ExtendedGrabScrollConfig(scroll_sensitivity=250.0),
)

CONSERVATIVE_PROFILE = AppConfig(
    camera=_base_camera,
    view=_base_view,
    pointer=PointerConfig(
        control_region=ControlRegion(left=0.10, top=0.10, right=0.90, bottom=0.90),
        g_hi=2.0,
    ),
    shortcut=ShortcutConfig(
        min_distance=0.25,
        max_duration_ms=700,
        cooldown_ms=1000,
        axis_ratio=1.8,
    ),
    clutch=_base_clutch,
    gesture_switches=_base_switches,
    gesture_config=ExtendedGestureConfig(pinch_close_ratio=0.4, pinch_open_ratio=0.6),
    grab_scroll_config=ExtendedGrabScrollConfig(scroll_sensitivity=100.0),
)

PROFILES = {
    "default": DEFAULT_PROFILE,
    "aggressive": AGGRESSIVE_PROFILE,
    "conservative": CONSERVATIVE_PROFILE,
}

def get_profile(name: str) -> AppConfig:
    return PROFILES.get(name.lower(), DEFAULT_PROFILE)
