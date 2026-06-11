from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import hypot

from handmouse.types import FramePoint
from handmouse.interlock import InteractionInterlock, InterlockType
from handmouse.policy.gesture_policy import GestureCandidate, RiskClass
from handmouse.tracking.observation import HandObservation


@dataclass(frozen=True)
class GrabScrollConfig:
    hold_ms: int = 120
    release_grace_ms: int = 120
    dead_zone: float = 0.015
    scroll_sensitivity: float = 180.0
    max_scroll_per_frame: int = 100
    thumb_index_max_distance: float = 1.8
    curled_finger_ratio: float = 1.65
    min_curled_fingers: int = 3
    post_release_grace_ms: int = 120
    only_active_when_draging: bool = True


class GrabScrollState(Enum):
    NO_HAND = auto()
    CANDIDATE = auto()
    GRABBING = auto()
    DRAGGING = auto()
    RELEASED = auto()


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

    def __init__(self, config: GrabScrollConfig, interlock: InteractionInterlock | None = None) -> None:
        self.config = config
        self.interlock = interlock
        self._state = GrabScrollState.NO_HAND
        self._candidate_started_ms: int | None = None
        self._last_seen_grab_ms: int | None = None
        self._released_at_ms: int | None = None
        self._anchor: FramePoint | None = None
        self._previous: FramePoint | None = None

    def update(self, obs: HandObservation | None, now_ms: int) -> list[GestureCandidate]:
        self._expire_release(now_ms)

        if obs is None or not obs.image_landmarks:
            return self._handle_missing_hand(now_ms)

        landmarks = obs.image_landmarks
        center = _hand_center(landmarks)
        if center is None:
            return self._handle_missing_hand(now_ms)

        is_grab = self._is_grab_pose(landmarks)

        wants_active = is_grab or self._state != GrabScrollState.NO_HAND
        if wants_active:
            if self.interlock:
                self.interlock.force_acquire(InterlockType.GRAB)
        else:
            if self.interlock:
                self.interlock.release(InterlockType.GRAB)

        if not is_grab:
            return self._handle_non_grab(now_ms)

        return self._handle_grab(center, now_ms)

    def reset(self) -> None:
        self._state = GrabScrollState.NO_HAND
        self._candidate_started_ms = None
        self._last_seen_grab_ms = None
        self._released_at_ms = None
        self._anchor = None
        self._previous = None
        if self.interlock:
            self.interlock.release(InterlockType.GRAB)

    def _handle_missing_hand(self, now_ms: int) -> list[GestureCandidate]:
        if self._last_seen_grab_ms is None and self._released_at_ms is None:
            self._state = GrabScrollState.NO_HAND
            if self.interlock:
                self.interlock.release(InterlockType.GRAB)
            return []

        if self._last_seen_grab_ms is not None and now_ms - self._last_seen_grab_ms >= self.config.release_grace_ms:
            self._begin_release(now_ms)

        self._state = GrabScrollState.RELEASED
        return []

    def _handle_non_grab(self, now_ms: int) -> list[GestureCandidate]:
        if self._last_seen_grab_ms is None and self._released_at_ms is None:
            self._state = GrabScrollState.NO_HAND
            return []

        if self._last_seen_grab_ms is not None and now_ms - self._last_seen_grab_ms >= self.config.release_grace_ms:
            self._begin_release(now_ms)

        self._state = GrabScrollState.RELEASED
        return []

    def _handle_grab(self, center: FramePoint, now_ms: int) -> list[GestureCandidate]:
        self._last_seen_grab_ms = now_ms

        if self._candidate_started_ms is None or self._anchor is None:
            self._candidate_started_ms = now_ms
            self._anchor = center
            self._previous = center
            self._state = GrabScrollState.CANDIDATE
            self._released_at_ms = None
            return []

        if now_ms - self._candidate_started_ms < self.config.hold_ms:
            self._previous = center
            self._state = GrabScrollState.CANDIDATE
            self._released_at_ms = None
            return []

        previous = self._previous or center
        self._previous = center
        frame_delta_y = center.y - previous.y
        scroll_delta = self._scroll_delta(frame_delta_y)
        self.last_scroll_delta = scroll_delta
        state = GrabScrollState.DRAGGING if scroll_delta else GrabScrollState.GRABBING
        self._state = state
        self._released_at_ms = None

        candidates = []
        if state == GrabScrollState.DRAGGING and scroll_delta != 0:
            candidates.append(GestureCandidate(
                detector="grab_scroll",
                gesture="scroll",
                phase="fire",
                confidence=1.0,
                risk=RiskClass.LOW,
                exclusive=True,
                measurements={"delta": scroll_delta}
            ))

        return candidates

    def _begin_release(self, now_ms: int) -> None:
        self._state = GrabScrollState.RELEASED
        if self._released_at_ms is None:
            self._released_at_ms = now_ms

    def _expire_release(self, now_ms: int) -> None:
        if self._released_at_ms is None:
            return

        if now_ms - self._released_at_ms < self.config.post_release_grace_ms:
            return

        self._candidate_started_ms = None
        self._last_seen_grab_ms = None
        self._released_at_ms = None
        self._anchor = None
        self._previous = None
        self._state = GrabScrollState.NO_HAND

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
    "GrabScrollConfig",
    "GrabScrollDetector",
    "GrabScrollState",
]
