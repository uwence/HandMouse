from dataclasses import dataclass
import json
import os

SUPPORTED_BACKENDS: tuple[str, ...] = ("CAP_DSHOW", "CAP_MSMF", "CAP_ANY")


@dataclass(frozen=True)
class CameraConfig:
    width: int
    height: int
    index: int
    backend_preference: tuple[str, ...] = SUPPORTED_BACKENDS
    buffer_size: int = 1
    fps_target: int = 60
    mirror_input: bool = True


@dataclass(frozen=True)
class ControlRegion:
    """Normalized frame coordinates, where 0.0 to 1.0 spans the camera frame."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class PointerConfig:
    control_region: ControlRegion
    g_hi: float = 3.0  # pointer speed/gain max


@dataclass(frozen=True)
class ShortcutConfig:
    min_distance: float
    max_duration_ms: int
    cooldown_ms: int
    axis_ratio: float


@dataclass(frozen=True)
class ClutchConfig:
    key_name: str = "ctrl_r"


@dataclass(frozen=True)
class GestureSwitches:
    right_click: bool = True
    double_click: bool = True
    drag_drop: bool = True
    alt_tab: bool = True
    win_d: bool = True


@dataclass(frozen=True)
class ExtendedGestureConfig:
    pinch_close: float = 0.05
    pinch_open: float = 0.075


@dataclass(frozen=True)
class ExtendedGrabScrollConfig:
    scroll_sensitivity: float = 180.0


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig
    pointer: PointerConfig
    shortcut: ShortcutConfig
    clutch: ClutchConfig
    gesture_switches: GestureSwitches = GestureSwitches()
    gesture_config: ExtendedGestureConfig = ExtendedGestureConfig()
    grab_scroll_config: ExtendedGrabScrollConfig = ExtendedGrabScrollConfig()


DEFAULT_CONFIG = AppConfig(
    camera=CameraConfig(
        width=640,
        height=480,
        index=0,
        backend_preference=SUPPORTED_BACKENDS,
        buffer_size=1,
        fps_target=60,
        mirror_input=True,
    ),
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
    clutch=ClutchConfig(
        key_name="ctrl_r",
    ),
    gesture_switches=GestureSwitches(),
    gesture_config=ExtendedGestureConfig(),
    grab_scroll_config=ExtendedGrabScrollConfig(),
)

CONFIG_PATH = os.path.expanduser("~/.handmouse/config.json")


def dataclass_to_dict(obj):
    import dataclasses
    if dataclasses.is_dataclass(obj):
        result = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            result[f.name] = dataclass_to_dict(value)
        return result
    elif isinstance(obj, tuple):
        return tuple(dataclass_to_dict(x) for x in obj)
    elif isinstance(obj, list):
        return [dataclass_to_dict(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    else:
        return obj


def dict_to_app_config(d: dict) -> AppConfig:
    cam_d = d.get("camera", {})
    camera = CameraConfig(
        width=cam_d.get("width", 640),
        height=cam_d.get("height", 480),
        index=cam_d.get("index", 0),
        backend_preference=tuple(cam_d.get("backend_preference", SUPPORTED_BACKENDS)),
        buffer_size=cam_d.get("buffer_size", 1),
        fps_target=cam_d.get("fps_target", 60),
        mirror_input=cam_d.get("mirror_input", True),
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
        pinch_close=gcfg_d.get("pinch_close", 0.05),
        pinch_open=gcfg_d.get("pinch_open", 0.075),
    )

    gscfg_d = d.get("grab_scroll_config", {})
    grab_scroll_config = ExtendedGrabScrollConfig(
        scroll_sensitivity=gscfg_d.get("scroll_sensitivity", 180.0),
    )

    return AppConfig(
        camera=camera,
        pointer=pointer,
        shortcut=shortcut,
        clutch=clutch,
        gesture_switches=gesture_switches,
        gesture_config=gesture_config,
        grab_scroll_config=grab_scroll_config,
    )


def load_or_create_config(path: str = CONFIG_PATH) -> AppConfig:
    if not os.path.exists(path):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            save_config(DEFAULT_CONFIG, path)
        except Exception as exc:
            print(f"WARNING: failed to create config directory/file: {exc}")
        return DEFAULT_CONFIG
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
            return dict_to_app_config(d)
    except Exception as exc:
        print(f"WARNING: failed to load config from {path}: {exc}. Using defaults.")
        return DEFAULT_CONFIG

ACTIVE_CONFIG = load_or_create_config()


def save_config(config: AppConfig, path: str = CONFIG_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(dataclass_to_dict(config), f, indent=4)
    except Exception as exc:
        print(f"ERROR: failed to save config to {path}: {exc}")
