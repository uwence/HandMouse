from __future__ import annotations

from math import hypot

from handmouse.tracking.observation import HandObservation


class PoseDetector:
    # Palm-center landmark indices (wrist + 4 MCP knuckles)
    _PALM_INDICES = (0, 5, 9, 13, 17)
    # (tip_index, mcp_index) pairs for each finger
    _FINGER_PAIRS = ((8, 5), (12, 9), (16, 13), (20, 17))
    # Ratio: tip_dist_from_palm / mcp_dist_from_palm must exceed this to be "extended"
    _EXTENDED_RATIO = 1.35
    # Ratio must be below this for "curled"
    _CURLED_RATIO = 1.10
    # Minimum fingers extended/curled to qualify
    _MIN_FINGERS = 3

    @classmethod
    def is_palm_open(cls, obs: HandObservation) -> bool:
        """True when >= 3 of 4 fingers are extended away from palm center."""
        lm = obs.image_landmarks
        if len(lm) < 21:
            return False
        palm_x, palm_y = cls._palm_center(lm)
        extended = sum(
            1 for tip_i, mcp_i in cls._FINGER_PAIRS
            if cls._is_extended(lm, tip_i, mcp_i, palm_x, palm_y)
        )
        return extended >= cls._MIN_FINGERS

    @classmethod
    def is_fist(cls, obs: HandObservation) -> bool:
        """True when >= 3 of 4 fingers are curled toward palm center."""
        lm = obs.image_landmarks
        if len(lm) < 21:
            return False
        palm_x, palm_y = cls._palm_center(lm)
        curled = sum(
            1 for tip_i, mcp_i in cls._FINGER_PAIRS
            if cls._is_curled(lm, tip_i, mcp_i, palm_x, palm_y)
        )
        return curled >= cls._MIN_FINGERS

    @classmethod
    def _palm_center(cls, lm: list) -> tuple[float, float]:
        xs = [lm[i].x for i in cls._PALM_INDICES]
        ys = [lm[i].y for i in cls._PALM_INDICES]
        n = len(cls._PALM_INDICES)
        return sum(xs) / n, sum(ys) / n

    @classmethod
    def _is_extended(cls, lm: list, tip_i: int, mcp_i: int, px: float, py: float) -> bool:
        tip_d = hypot(lm[tip_i].x - px, lm[tip_i].y - py)
        mcp_d = hypot(lm[mcp_i].x - px, lm[mcp_i].y - py)
        return mcp_d > 0 and tip_d / mcp_d >= cls._EXTENDED_RATIO

    @classmethod
    def _is_curled(cls, lm: list, tip_i: int, mcp_i: int, px: float, py: float) -> bool:
        tip_d = hypot(lm[tip_i].x - px, lm[tip_i].y - py)
        mcp_d = hypot(lm[mcp_i].x - px, lm[mcp_i].y - py)
        return mcp_d > 0 and tip_d / mcp_d <= cls._CURLED_RATIO


__all__ = ["PoseDetector"]
