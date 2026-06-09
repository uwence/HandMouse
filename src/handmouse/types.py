from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from handmouse.config import PointerConfig


@dataclass(frozen=True)
class FramePoint:
    x: float
    y: float


@dataclass(frozen=True)
class ScreenPoint:
    x: int
    y: int


@dataclass(frozen=True)
class ScreenDelta:
    dx: int
    dy: int


__all__ = [
    "FramePoint",
    "ScreenDelta",
    "ScreenPoint",
]
