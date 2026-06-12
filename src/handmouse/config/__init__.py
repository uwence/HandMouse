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
    input_is_mirrored: bool = False
    running_mode: str = "video"  # "video" or "live_stream"

@dataclass(frozen=True)
class ViewConfig:
    render_mirrored: bool = True


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
    win_d: bool = False


@dataclass(frozen=True)
class ExtendedGestureConfig:
    pinch_close_ratio: float = 0.5
    pinch_open_ratio: float = 0.7


@dataclass(frozen=True)
class ExtendedGrabScrollConfig:
    scroll_sensitivity: float = 180.0


@dataclass(frozen=True)
class PolicyConfig:
    high_risk_cooldown_ms: int = 500
    explicit_confirm_required: bool = True


@dataclass(frozen=True)
class BimanualConfig:
    enabled: bool = False
    dominant_hand: str = "right"
    open_hold_ms: int = 250
    open_stable_frames: int = 4
    suspend_grace_ms: int = 150
    idle_grace_ms: int = 500
    identity_grace_ms: int = 500


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig
    pointer: PointerConfig
    shortcut: ShortcutConfig
    clutch: ClutchConfig
    schema_version: int = 2
    policy: PolicyConfig = PolicyConfig()
    gesture_switches: GestureSwitches = GestureSwitches()
    gesture_config: ExtendedGestureConfig = ExtendedGestureConfig()
    grab_scroll_config: ExtendedGrabScrollConfig = ExtendedGrabScrollConfig()
    view: ViewConfig = ViewConfig()
    show_osd: bool = True
    bimanual: BimanualConfig = BimanualConfig()


DEFAULT_CONFIG = AppConfig(
    camera=CameraConfig(
        width=640,
        height=480,
        index=0,
        backend_preference=SUPPORTED_BACKENDS,
        buffer_size=1,
        fps_target=60,
        input_is_mirrored=False,
    ),
    view=ViewConfig(
        render_mirrored=True,
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
    schema_version=2,
    policy=PolicyConfig(),
    gesture_switches=GestureSwitches(),
    gesture_config=ExtendedGestureConfig(),
    grab_scroll_config=ExtendedGrabScrollConfig(),
    bimanual=BimanualConfig(),
)

CONFIG_DIR = os.path.expanduser("~/.handmouse")
CONFIG_PATH_YAML = os.path.join(CONFIG_DIR, "config.yaml")
CONFIG_PATH_JSON = os.path.join(CONFIG_DIR, "config.json")

from .schema import dict_to_app_config, dataclass_to_dict

def load_or_create_config(path: str | None = None) -> AppConfig:
    import yaml
    
    target_yaml = path if path is not None else CONFIG_PATH_YAML
    target_dir = os.path.dirname(target_yaml)
    os.makedirs(target_dir, exist_ok=True)
    
    # Check for yaml config first
    if os.path.exists(target_yaml):
        try:
            with open(target_yaml, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
                return dict_to_app_config(d)
        except Exception as exc:
            print(f"WARNING: failed to load YAML config: {exc}. Using defaults.")
            return DEFAULT_CONFIG
            
    # Check if we need to migrate from JSON (only if path wasn't explicitly provided)
    if path is None and os.path.exists(CONFIG_PATH_JSON):
        try:
            import json
            print("Migrating config from JSON to YAML...")
            with open(CONFIG_PATH_JSON, "r", encoding="utf-8") as f:
                d = json.load(f)
            config = dict_to_app_config(d)
            # Save it immediately as YAML
            save_config(config)
            return config
        except Exception as exc:
            print(f"WARNING: failed to migrate JSON config: {exc}. Using defaults.")
    
    # Create default YAML config
    save_config(DEFAULT_CONFIG, path=target_yaml)
    return DEFAULT_CONFIG

def save_config(config: AppConfig, path: str | None = None) -> None:
    import yaml
    target_yaml = path if path is not None else CONFIG_PATH_YAML
    target_dir = os.path.dirname(target_yaml)
    try:
        os.makedirs(target_dir, exist_ok=True)
        with open(target_yaml, "w", encoding="utf-8") as f:
            yaml.dump(dataclass_to_dict(config), f, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        print(f"ERROR: failed to save config to {target_yaml}: {exc}")

ACTIVE_CONFIG = load_or_create_config()
