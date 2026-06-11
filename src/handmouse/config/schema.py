import dataclasses
from typing import Any

from handmouse.config import (
    CameraConfig, ViewConfig, ControlRegion, PointerConfig,
    ShortcutConfig, ClutchConfig, GestureSwitches,
    ExtendedGestureConfig, ExtendedGrabScrollConfig, PolicyConfig, AppConfig,
    SUPPORTED_BACKENDS
)

# Move dict_to_app_config and dataclass_to_dict here to centralize schema logic
def dataclass_to_dict(obj: Any) -> Any:
    if dataclasses.is_dataclass(obj):
        result = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = dataclass_to_dict(value)
        return result
    elif isinstance(obj, tuple):
        return [dataclass_to_dict(x) for x in obj]
    elif isinstance(obj, list):
        return [dataclass_to_dict(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    else:
        return obj

def dict_to_app_config(d: dict) -> AppConfig:
    schema_version = int(d.get("schema_version", 2))
    if schema_version < 1:
        raise ValueError("schema_version must be >= 1")

    cam_d = d.get("camera", {})
    camera = CameraConfig(
        width=cam_d.get("width", 640),
        height=cam_d.get("height", 480),
        index=cam_d.get("index", 0),
        backend_preference=tuple(cam_d.get("backend_preference", SUPPORTED_BACKENDS)),
        buffer_size=cam_d.get("buffer_size", 1),
        fps_target=cam_d.get("fps_target", 60),
        input_is_mirrored=cam_d.get("input_is_mirrored", cam_d.get("mirror_input", False)),
        running_mode=cam_d.get("running_mode", "video"),
    )
    
    view_d = d.get("view", {})
    view = ViewConfig(
        render_mirrored=view_d.get("render_mirrored", d.get("camera", {}).get("mirror_input", True))
    )

    ptr_d = d.get("pointer", {})
    cr_d = ptr_d.get("control_region", {})
    control_region = ControlRegion(
        left=cr_d.get("left", 0.12),
        top=cr_d.get("top", 0.10),
        right=cr_d.get("right", 0.88),
        bottom=cr_d.get("bottom", 0.90),
    )
    pointer = PointerConfig(
        control_region=control_region,
        g_hi=ptr_d.get("g_hi", 3.0),
    )

    sh_d = d.get("shortcut", {})
    shortcut = ShortcutConfig(
        min_distance=sh_d.get("min_distance", 0.18),
        max_duration_ms=sh_d.get("max_duration_ms", 900),
        cooldown_ms=sh_d.get("cooldown_ms", 700),
        axis_ratio=sh_d.get("axis_ratio", 1.4),
    )

    cl_d = d.get("clutch", {})
    clutch = ClutchConfig(
        key_name=cl_d.get("key_name", "ctrl_r"),
    )

    sw_d = d.get("gesture_switches", {})
    gesture_switches = GestureSwitches(
        right_click=sw_d.get("right_click", True),
        double_click=sw_d.get("double_click", True),
        drag_drop=sw_d.get("drag_drop", True),
        alt_tab=sw_d.get("alt_tab", True),
        win_d=sw_d.get("win_d", True),
    )

    gcfg_d = d.get("gesture_config", {})
    gesture_config = ExtendedGestureConfig(
        pinch_close_ratio=gcfg_d.get("pinch_close_ratio", gcfg_d.get("pinch_close", 0.5)),
        pinch_open_ratio=gcfg_d.get("pinch_open_ratio", gcfg_d.get("pinch_open", 0.7)),
    )

    gscfg_d = d.get("grab_scroll_config", {})
    grab_scroll_config = ExtendedGrabScrollConfig(
        scroll_sensitivity=gscfg_d.get("scroll_sensitivity", 180.0),
    )

    policy_d = d.get("policy", {})
    high_risk_cooldown_ms = int(policy_d.get("high_risk_cooldown_ms", 500))
    if high_risk_cooldown_ms < 0:
        raise ValueError("policy.high_risk_cooldown_ms must be >= 0")
    policy = PolicyConfig(
        high_risk_cooldown_ms=high_risk_cooldown_ms,
        explicit_confirm_required=bool(policy_d.get("explicit_confirm_required", True)),
    )

    return AppConfig(
        camera=camera,
        pointer=pointer,
        shortcut=shortcut,
        clutch=clutch,
        schema_version=schema_version,
        policy=policy,
        gesture_switches=gesture_switches,
        gesture_config=gesture_config,
        grab_scroll_config=grab_scroll_config,
        view=view,
        show_osd=d.get("show_osd", True),
    )
