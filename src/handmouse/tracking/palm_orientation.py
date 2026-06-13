from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from handmouse.tracking.observation import HandObservation, Point3


_WRIST = 0
_INDEX_MCP = 5
_PINKY_MCP = 17

DEFAULT_NORMAL_Z_MIN = 0.35


@dataclass(frozen=True)
class PalmOrientation:
    """Palm orientation derived from MediaPipe world landmarks.

    ``normal`` is a unit vector perpendicular to the palm plane in
    MediaPipe world space (meters, camera-relative). ``normal_z`` is the
    camera-axis component: ``|z| ~= 1`` means the palm faces roughly
    toward or away from the camera; ``|z| ~= 0`` means the palm is
    edge-on (sideways).
    """

    normal: Point3
    normal_z: float
    is_valid: bool


def compute_palm_orientation(
    obs: HandObservation | None,
    *,
    normal_z_min: float = DEFAULT_NORMAL_Z_MIN,
) -> PalmOrientation | None:
    """Compute palm orientation from world landmarks.

    Returns ``None`` when ``obs`` has no world landmarks or too few
    points, so callers can preserve their existing behavior when the
    3D signal is unavailable.
    """
    if obs is None:
        return None
    world = obs.world_landmarks
    if not world or len(world) <= max(_WRIST, _INDEX_MCP, _PINKY_MCP):
        return None

    wrist = world[_WRIST]
    index_mcp = world[_INDEX_MCP]
    pinky_mcp = world[_PINKY_MCP]

    ax = index_mcp.x - wrist.x
    ay = index_mcp.y - wrist.y
    az = index_mcp.z - wrist.z
    bx = pinky_mcp.x - wrist.x
    by = pinky_mcp.y - wrist.y
    bz = pinky_mcp.z - wrist.z

    nx = ay * bz - az * by
    ny = az * bx - ax * bz
    nz = ax * by - ay * bx

    mag = sqrt(nx * nx + ny * ny + nz * nz)
    if mag <= 1e-9:
        return PalmOrientation(
            normal=Point3(0.0, 0.0, 0.0),
            normal_z=0.0,
            is_valid=False,
        )

    nx /= mag
    ny /= mag
    nz /= mag

    return PalmOrientation(
        normal=Point3(nx, ny, nz),
        normal_z=nz,
        is_valid=abs(nz) >= normal_z_min,
    )


__all__ = ["PalmOrientation", "compute_palm_orientation", "DEFAULT_NORMAL_Z_MIN"]
