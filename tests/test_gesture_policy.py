from __future__ import annotations

from dataclasses import replace

import pytest

import handmouse.config as config_module
from handmouse.config import GestureSwitches
from handmouse.policy.gesture_policy import GestureCandidate, GesturePolicy, RiskClass
from handmouse.tracking.observation import TrackingQuality


def make_quality(*, ok: bool, score: float = 1.0) -> TrackingQuality:
    return TrackingQuality(
        ok=ok,
        score=score,
        reasons=(),
        palm_span_px=120.0,
        handedness_ok=True,
        stable_frames=6,
        lost_frames=0,
    )


def make_candidate(action: str, risk: RiskClass, **measurements: float) -> GestureCandidate:
    return GestureCandidate(
        detector="test",
        gesture=action,
        phase="fire",
        confidence=1.0,
        risk=risk,
        exclusive=True,
        measurements=measurements,
    )


@pytest.mark.parametrize(
    ("switch_name", "action", "risk"),
    [
        ("right_click", "click_right", RiskClass.MEDIUM),
        ("double_click", "double_click", RiskClass.MEDIUM),
        ("drag_drop", "drag_hold", RiskClass.MEDIUM),
        ("alt_tab", "task_view", RiskClass.HIGH),
        ("win_d", "swipe_left_palm", RiskClass.HIGH),
    ],
)
def test_policy_blocks_disabled_feature_switches(
    monkeypatch: pytest.MonkeyPatch,
    switch_name: str,
    action: str,
    risk: RiskClass,
) -> None:
    switches = replace(GestureSwitches(), **{switch_name: False})
    monkeypatch.setattr(
        config_module,
        "ACTIVE_CONFIG",
        replace(config_module.ACTIVE_CONFIG, gesture_switches=switches),
    )
    policy = GesturePolicy()

    intents = policy.evaluate(None, make_quality(ok=True), [make_candidate(action, risk)], {})

    assert intents == []


def test_policy_blocks_medium_risk_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    intents = policy.evaluate(
        None,
        make_quality(ok=False, score=0.25),
        [make_candidate("click_left", RiskClass.MEDIUM)],
        {},
    )

    assert intents == []


def test_policy_allows_drag_release_even_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    intents = policy.evaluate(
        None,
        make_quality(ok=False, score=0.25),
        [make_candidate("drag_release", RiskClass.MEDIUM)],
        {},
    )

    assert [intent.action for intent in intents] == ["drag_release"]


def test_policy_requires_explicit_confirm_for_task_view_commit() -> None:
    policy = GesturePolicy()

    intents = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view_commit", RiskClass.HIGH)],
        {},
    )

    assert intents == []


def test_policy_allows_explicit_confirmed_task_view_commit() -> None:
    policy = GesturePolicy()

    intents = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view_commit", RiskClass.HIGH, explicit_confirm=1.0)],
        {},
    )

    assert [intent.action for intent in intents] == ["task_view_commit"]


def test_policy_allows_task_view_cancel_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    intents = policy.evaluate(
        None,
        make_quality(ok=False, score=0.1),
        [make_candidate("task_view_cancel", RiskClass.HIGH)],
        {},
    )

    assert [intent.action for intent in intents] == ["task_view_cancel"]
