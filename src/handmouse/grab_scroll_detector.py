from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.config import GrabScrollConfig
from handmouse.pointer_mapper import FramePoint


class GrabScrollState(Enum):
    NO_HAND = auto()
    CANDIDATE = auto()
    GRABBING = auto()
    DRAGGING = auto()
    RELEASED = auto()


@dataclass(frozen=True)
class GrabScrollResult:
    state: GrabScrollState
    active: bool
    scroll_delta: int
    displacement_x: float | None
    displacement_y: float | None
    is_grab_pose: bool


class GrabScrollDetector:
    WRIST = 0
    THUMB_TIP = 4
    INDEX_MCP = 5
    INDEX_TIP = 8
    MIDDLE_MCP = 9
    MIDDLE_TIP = 12
    RING_MCP = 13
    RING_TIP = 16
    PINKY_MCP = 17
    PINKY_TIP = 20

    def __init__(self, config: GrabScrollConfig) -> None:
        self.config = config
        self._candidate_started_ms: int | None = None
        self._last_seen_grab_ms: int | None = None
        self._anchor: FramePoint | None = None
        self._previous: FramePoint | None = None

    def update(
        self,
        landmarks: list[FramePoint] | None,
        now_ms: int,
    ) -> GrabScrollResult:
        if not landmarks:
            self.reset()
            return GrabScrollResult(
                GrabScrollState.NO_HAND,
                False,
                0,
                None,
                None,
                False,
            )

        center = _hand_center(landmarks)
        if center is None:
            self.reset()
            return GrabScrollResult(
                GrabScrollState.NO_HAND,
                False,
                0,
                None,
                None,
                False,
            )

        is_grab = self._is_grab_pose(landmarks)
        if not is_grab:
            if self._should_release(now_ms):
                self.reset()
                return GrabScrollResult(
                    GrabScrollState.RELEASED,
                    False,
                    0,
                    None,
                    None,
                    False,
                )

            return GrabScrollResult(
                GrabScrollState.GRABBING,
                True,
                0,
                0.0,
                0.0,
                False,
            )

        self._last_seen_grab_ms = now_ms
        if self._candidate_started_ms is None:
            self._candidate_started_ms = now_ms
            self._anchor = center
            self._previous = center
            return GrabScrollResult(
                GrabScrollState.CANDIDATE,
                False,
                0,
                0.0,
                0.0,
                True,
            )

        if now_ms - self._candidate_started_ms < self.config.hold_ms:
            self._previous = center
            return GrabScrollResult(
                GrabScrollState.CANDIDATE,
                False,
                0,
                0.0,
                0.0,
                True,
            )

        previous = self._previous or center
        self._previous = center
        dx = center.x - (self._anchor or center).x
        dy = center.y - (self._anchor or center).y
        frame_delta_y = center.y - previous.y
        scroll_delta = self._scroll_delta(frame_delta_y)
        state = GrabScrollState.DRAGGING if scroll_delta else GrabScrollState.GRABBING
        return GrabScrollResult(
            state,
            True,
            scroll_delta,
            dx,
            dy,
            True,
        )

    def reset(self) -> None:
        self._candidate_started_ms = None
        self._last_seen_grab_ms = None
        self._anchor = None
        self._previous = None

    def _should_release(self, now_ms: int) -> bool:
        if self._last_seen_grab_ms is None:
            return True

        return now_ms - self._last_seen_grab_ms >= self.config.release_grace_ms

    def _scroll_delta(self, frame_delta_y: float) -> int:
        if abs(frame_delta_y) < self.config.dead_zone:
            return 0

        value = round(-frame_delta_y * self.config.scroll_sensitivity)
        return max(
            -self.config.max_scroll_per_frame,
            min(self.config.max_scroll_per_frame, value),
        )

    def _is_grab_pose(self, landmarks: list[FramePoint]) -> bool:
        required = [
            self.WRIST,
            self.THUMB_TIP,
            self.INDEX_MCP,
            self.INDEX_TIP,
            self.MIDDLE_MCP,
            self.MIDDLE_TIP,
            self.RING_MCP,
            self.RING_TIP,
            self.PINKY_MCP,
            self.PINKY_TIP,
        ]
        if any(index >= len(landmarks) for index in required):
            return False

        palm_center = _palm_center(landmarks)
        palm_scale = _distance(landmarks[self.WRIST], landmarks[self.MIDDLE_MCP])
        if palm_center is None or palm_scale <= 0:
            return False

        thumb_index_distance = (
            _distance(landmarks[self.THUMB_TIP], landmarks[self.INDEX_TIP])
            / palm_scale
        )
        if thumb_index_distance > self.config.thumb_index_max_distance:
            return False

        curled_count = 0
        for mcp_index, tip_index in (
            (self.INDEX_MCP, self.INDEX_TIP),
            (self.MIDDLE_MCP, self.MIDDLE_TIP),
            (self.RING_MCP, self.RING_TIP),
            (self.PINKY_MCP, self.PINKY_TIP),
        ):
            mcp_distance = _distance(landmarks[mcp_index], palm_center)
            tip_distance = _distance(landmarks[tip_index], palm_center)
            if mcp_distance <= 0:
                continue
            if tip_distance / mcp_distance <= self.config.curled_finger_ratio:
                curled_count += 1

        return curled_count >= self.config.min_curled_fingers


def _hand_center(landmarks: list[FramePoint]) -> FramePoint | None:
    points = [landmarks[index] for index in (0, 5, 9, 13, 17) if index < len(landmarks)]
    if not points:
        return None

    return FramePoint(
        sum(point.x for point in points) / len(points),
        sum(point.y for point in points) / len(points),
    )


def _palm_center(landmarks: list[FramePoint]) -> FramePoint | None:
    return _hand_center(landmarks)


def _distance(a: FramePoint, b: FramePoint) -> float:
    return hypot(a.x - b.x, a.y - b.y)


__all__ = [
    "GrabScrollDetector",
    "GrabScrollResult",
    "GrabScrollState",
]
