from __future__ import annotations

from handmouse.tracking.observation import HandObservation, TrackingQuality

class TrackingQualityGate:
    def __init__(
        self, 
        max_stale_ms: int = 80, 
        min_palm_span_px: float = 90.0, 
        min_stable_frames: int = 4, 
        handedness_min_score: float = 0.75
    ):
        self.max_stale_ms = max_stale_ms
        self.min_palm_span_px = min_palm_span_px
        self.min_stable_frames = min_stable_frames
        self.handedness_min_score = handedness_min_score
        
        self._stable_frames = 0
        self._lost_frames = 0
        self._last_frame_had_hand = False

    def update(self, obs: HandObservation | None, frame_width: int, frame_height: int) -> TrackingQuality:
        if obs is None or not obs.image_landmarks or len(obs.image_landmarks) < 21:
            self._lost_frames += 1
            self._stable_frames = 0
            self._last_frame_had_hand = False
            return TrackingQuality(
                ok=False,
                score=0.0,
                reasons=("no_hand",),
                palm_span_px=None,
                handedness_ok=False,
                stable_frames=0,
                lost_frames=self._lost_frames,
            )

        self._lost_frames = 0
        self._stable_frames += 1
        self._last_frame_had_hand = True

        reasons = []
        
        if obs.stale_ms > self.max_stale_ms:
            reasons.append("stale")
            
        if self._stable_frames < self.min_stable_frames:
            reasons.append("unstable")

        # calculate palm span
        index_mcp = obs.image_landmarks[5]
        pinky_mcp = obs.image_landmarks[17]
        # Landmarks are normalized to the camera frame, not the desktop screen.
        span_x = (index_mcp.x - pinky_mcp.x) * frame_width
        span_y = (index_mcp.y - pinky_mcp.y) * frame_height
        palm_span_px = (span_x ** 2 + span_y ** 2) ** 0.5
        
        if palm_span_px < self.min_palm_span_px:
            reasons.append("palm_too_small")

        handedness_ok = (
            obs.handedness_score is not None 
            and obs.handedness_score >= self.handedness_min_score 
            and obs.handedness_label is not None
        )
        if not handedness_ok:
            reasons.append("handedness_uncertain")

        penalties = 0.0
        if "stale" in reasons:
            penalties += 0.45
        if "unstable" in reasons:
            penalties += 0.30
        if "palm_too_small" in reasons:
            penalties += 0.25
        if "handedness_uncertain" in reasons:
            penalties += 0.20

        score = max(0.0, 1.0 - penalties)
        ok = len(reasons) == 0

        return TrackingQuality(
            ok=ok,
            score=score,
            reasons=tuple(reasons),
            palm_span_px=palm_span_px,
            handedness_ok=handedness_ok,
            stable_frames=self._stable_frames,
            lost_frames=0,
        )
