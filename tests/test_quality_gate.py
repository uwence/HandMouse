from __future__ import annotations

from handmouse.tracking.observation import HandObservation, Point3
from handmouse.tracking.quality_gate import TrackingQualityGate


def _obs(
    *,
    stale_ms: int = 0,
    span_x: float = 0.18,
    span_y: float = 0.10,
    score: float = 0.99,
) -> HandObservation:
    points = [Point3(0.5, 0.5, 0.01)] * 21
    points[5] = Point3(0.50, 0.50, 0.01)
    points[17] = Point3(0.50 + span_x, 0.50 + span_y, 0.01)
    return HandObservation(
        frame_id=1,
        ts_ms=1000,
        image_landmarks=points,
        world_landmarks=points,
        handedness_label="Left",
        handedness_score=score,
        raw_result=None,
        stale_ms=stale_ms,
        camera_space="mirrored",
    )


def test_quality_score_drops_for_stale_small_and_unstable_frames() -> None:
    gate = TrackingQualityGate(max_stale_ms=80, min_palm_span_px=90.0, min_stable_frames=4)
    result = gate.update(_obs(stale_ms=120, span_x=0.01, span_y=0.005), 1920, 1080)
    assert result.ok is False
    assert result.score < 0.5
    assert "stale" in result.reasons
    assert "palm_too_small" in result.reasons
    assert "unstable" in result.reasons


def test_quality_promotes_after_stable_sequence() -> None:
    gate = TrackingQualityGate(min_stable_frames=3)
    gate.update(_obs(), 1920, 1080)
    gate.update(_obs(), 1920, 1080)
    result = gate.update(_obs(), 1920, 1080)
    assert result.ok is True
    assert result.stable_frames == 3
    assert result.score >= 0.9
