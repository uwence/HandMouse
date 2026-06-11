from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Any


@dataclass(frozen=True)
class Point2:
    x: float
    y: float


@dataclass(frozen=True)
class Point3:
    x: float
    y: float
    z: float


@dataclass(frozen=True)
class HandObservation:
    frame_id: int
    ts_ms: int
    image_landmarks: list[Point3]              # x,y normalized; z image-depth
    world_landmarks: list[Point3] | None       # meters, if available
    handedness_label: Literal["Left", "Right"] | None
    handedness_score: float | None
    raw_result: Any | None
    stale_ms: int
    camera_space: Literal["mirrored", "physical"]


@dataclass(frozen=True)
class TrackingQuality:
    ok: bool
    score: float                # 0..1
    reasons: tuple[str, ...]
    palm_span_px: float | None
    handedness_ok: bool
    stable_frames: int
    lost_frames: int
