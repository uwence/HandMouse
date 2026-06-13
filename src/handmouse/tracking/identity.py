from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from handmouse.hand_tracker import HandTrackingResult, MultiHandTrackingResult
from handmouse.tracking.observation import HandObservation, Point3
from handmouse.types import FramePoint


@dataclass
class TrackedHand:
    label: str
    result: HandTrackingResult
    obs: HandObservation
    stable_frames: int
    lost_frames: int
    last_seen_ms: int


@dataclass(frozen=True)
class IdentifiedHands:
    left_result: HandTrackingResult | None
    right_result: HandTrackingResult | None
    left_obs: HandObservation | None
    right_obs: HandObservation | None
    left_stable_frames: int
    right_stable_frames: int


def _result_to_obs(
    result: HandTrackingResult,
    now_ms: int,
    frame_age_ms: int,
) -> HandObservation:
    raw_lm = getattr(result, "raw_landmarks", None)
    pts: list[Point3] = []
    for idx, lm in enumerate(result.landmarks):
        z = 0.0
        if raw_lm is not None and idx < len(raw_lm):
            z = float(getattr(raw_lm[idx], "z", 0.0))
        pts.append(Point3(x=lm.x, y=lm.y, z=z))
    return HandObservation(
        frame_id=0,
        ts_ms=now_ms,
        image_landmarks=pts,
        world_landmarks=result.world_landmarks,
        handedness_label=result.handedness_label,
        handedness_score=result.handedness_confidence,
        raw_result=result,
        stale_ms=frame_age_ms,
        camera_space="mirrored",
    )


class HandIdentityTracker:
    def __init__(self, grace_ms: int = 500, min_confidence: float = 0.75) -> None:
        self.grace_ms = grace_ms
        self.min_confidence = min_confidence
        self._left: TrackedHand | None = None
        self._right: TrackedHand | None = None

    def update(
        self,
        multi: MultiHandTrackingResult,
        now_ms: int,
        frame_age_ms: int,
    ) -> IdentifiedHands:
        seen: dict[str, tuple[HandTrackingResult, HandObservation]] = {}
        for h in multi.hands:
            if h.handedness_label not in ("Left", "Right") or not h.landmarks:
                continue
            score = h.handedness_confidence
            if score is not None and score < self.min_confidence:
                continue
            obs = _result_to_obs(h, now_ms, frame_age_ms)
            seen[h.handedness_label] = (h, obs)

        self._left = self._merge("Left", self._left, seen.get("Left"), now_ms)
        self._right = self._merge("Right", self._right, seen.get("Right"), now_ms)

        return IdentifiedHands(
            left_result=self._left.result if self._left else None,
            right_result=self._right.result if self._right else None,
            left_obs=self._left.obs if self._left else None,
            right_obs=self._right.obs if self._right else None,
            left_stable_frames=self._left.stable_frames if self._left else 0,
            right_stable_frames=self._right.stable_frames if self._right else 0,
        )

    def reset(self) -> None:
        self._left = None
        self._right = None

    def _merge(
        self,
        label: str,
        tracked: TrackedHand | None,
        seen: tuple[HandTrackingResult, HandObservation] | None,
        now_ms: int,
    ) -> TrackedHand | None:
        if seen is not None:
            result, obs = seen
            stable = (tracked.stable_frames + 1) if tracked else 1
            return TrackedHand(
                label=label,
                result=result,
                obs=obs,
                stable_frames=stable,
                lost_frames=0,
                last_seen_ms=now_ms,
            )
        if tracked is None:
            return None
        elapsed = now_ms - tracked.last_seen_ms
        if elapsed > self.grace_ms:
            return None
        return TrackedHand(
            label=label,
            result=tracked.result,
            obs=tracked.obs,
            stable_frames=tracked.stable_frames,
            lost_frames=tracked.lost_frames + 1,
            last_seen_ms=tracked.last_seen_ms,
        )


__all__ = ["HandIdentityTracker", "IdentifiedHands", "TrackedHand"]
