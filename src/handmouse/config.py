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


@dataclass(frozen=True)
class GestureConfig:
    # Thresholds are normalized distances, not pixels, so camera resolution can vary.
    pinch_threshold: float
    hold_ms: int
    cooldown_ms: int
    release_threshold: float


@dataclass(frozen=True)
class AppConfig:
    camera: CameraConfig
    pointer: PointerConfig
    gesture: GestureConfig


DEFAULT_CONFIG = AppConfig(
    camera=CameraConfig(width=1280, height=720, index=0),
    pointer=PointerConfig(
        smoothing=0.35,
        dead_zone_px=4.0,
        control_region=ControlRegion(left=0.0, top=0.0, right=1.0, bottom=1.0),
    ),
    gesture=GestureConfig(
        pinch_threshold=0.05,
        hold_ms=120,
        cooldown_ms=350,
        release_threshold=0.08,
    ),
)
