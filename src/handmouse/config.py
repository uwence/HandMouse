from dataclasses import dataclass


SUPPORTED_BACKENDS: tuple[str, ...] = ("CAP_DSHOW", "CAP_MSMF", "CAP_ANY")


@dataclass(frozen=True)
class CameraConfig:
    width: int
    height: int
    index: int
    backend_preference: tuple[str, ...] = SUPPORTED_BACKENDS
    buffer_size: int = 1
    fps_target: int = 60


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
class AppConfig:
    camera: CameraConfig
    pointer: PointerConfig
    shortcut: ShortcutConfig
    clutch: ClutchConfig


DEFAULT_CONFIG = AppConfig(
    camera=CameraConfig(
        width=640,
        height=480,
        index=0,
        backend_preference=SUPPORTED_BACKENDS,
        buffer_size=1,
        fps_target=60,
    ),
    pointer=PointerConfig(
        control_region=ControlRegion(left=0.12, top=0.10, right=0.88, bottom=0.90),
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
)
