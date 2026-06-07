from dataclasses import dataclass


@dataclass(frozen=True)
class CameraConfig:
    width: int
    height: int
    index: int


@dataclass(frozen=True)
class ControlRegion:
    """Normalized frame coordinates, where 0.0 to 1.0 spans the camera frame."""

    left: float
    top: float
    right: float
    bottom: float


@dataclass(frozen=True)
class PointerConfig:
    smoothing: float
    dead_zone_px: float
    control_region: ControlRegion
    relative_sensitivity: float = 1.4


@dataclass(frozen=True)
class GestureConfig:
    # Thresholds are normalized distances, not pixels, so camera resolution can vary.
    pinch_threshold: float
    hold_ms: int
    cooldown_ms: int
    release_threshold: float


@dataclass(frozen=True)
class ShortcutConfig:
    min_distance: float
    max_duration_ms: int
    cooldown_ms: int
    axis_ratio: float


@dataclass(frozen=True)
class GrabScrollConfig:
    hold_ms: int
    release_grace_ms: int
    dead_zone: float
    scroll_sensitivity: float
    max_scroll_per_frame: int
    thumb_index_max_distance: float
    curled_finger_ratio: float
    min_curled_fingers: int


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig
    pointer: PointerConfig
    gesture: GestureConfig
    shortcut: ShortcutConfig
    grab_scroll: GrabScrollConfig


DEFAULT_CONFIG = AppConfig(
    camera=CameraConfig(width=1280, height=720, index=0),
    pointer=PointerConfig(
        smoothing=0.35,
        dead_zone_px=4.0,
        control_region=ControlRegion(left=0.12, top=0.10, right=0.88, bottom=0.90),
        relative_sensitivity=1.4,
    ),
    gesture=GestureConfig(
        pinch_threshold=0.05,
        hold_ms=120,
        cooldown_ms=350,
        release_threshold=0.08,
    ),
    shortcut=ShortcutConfig(
        min_distance=0.18,
        max_duration_ms=900,
        cooldown_ms=700,
        axis_ratio=1.4,
    ),
    grab_scroll=GrabScrollConfig(
        hold_ms=120,
        release_grace_ms=120,
        dead_zone=0.015,
        scroll_sensitivity=180.0,
        max_scroll_per_frame=18,
        thumb_index_max_distance=1.8,
        curled_finger_ratio=1.65,
        min_curled_fingers=2,
    ),
)
