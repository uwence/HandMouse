from __future__ import annotations

from typing import Any


def build_frame_sample(
    *,
    ts_ms: int,
    frame_age_ms: int,
    pointer_dx: float,
    pointer_dy: float,
    landmarks: list[list[float]],
    world_landmarks: list[list[float]] | None,
    quality_score: float,
    quality_reasons: tuple[str, ...] | list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "ts_ms": ts_ms,
        "frame_age_ms": frame_age_ms,
        "pointer_dx": pointer_dx,
        "pointer_dy": pointer_dy,
        "landmarks": landmarks,
        "world_landmarks": world_landmarks,
        "quality_score": quality_score,
        "quality_reasons": list(quality_reasons),
        **extra,
    }


def build_gesture_candidate(
    *,
    ts_ms: int,
    detector: str,
    gesture: str,
    phase: str,
    confidence: float,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "ts_ms": ts_ms,
        "detector": detector,
        "gesture": gesture,
        "phase": phase,
        "confidence": confidence,
        **extra,
    }


def build_gesture_decision(
    *,
    ts_ms: int,
    action: str,
    risk: str,
    detector: str,
    committed: bool,
    blocked_by: str | None,
    quality_score: float,
    quality_reasons: tuple[str, ...] | list[str],
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "ts_ms": ts_ms,
        "action": action,
        "risk": risk,
        "detector": detector,
        "committed": committed,
        "blocked_by": blocked_by,
        "quality_score": quality_score,
        "quality_reasons": list(quality_reasons),
        **extra,
    }


def build_action_dispatch(
    *,
    action: str,
    executed: bool,
    blocked_by: str | None,
    latency_ms: int = 0,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "action": action,
        "executed": executed,
        "blocked_by": blocked_by,
        "latency_ms": latency_ms,
        **extra,
    }
