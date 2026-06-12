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

    decisions = policy.evaluate(None, make_quality(ok=True), [make_candidate(action, risk)], {})

    assert len(decisions) == 1
    assert decisions[0].committed is False
    assert decisions[0].payload["blocked_by"] == "feature_disabled"


def test_policy_blocks_medium_risk_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=False, score=0.25),
        [make_candidate("click_left", RiskClass.MEDIUM)],
        {},
    )

    assert len(decisions) == 1
    assert decisions[0].committed is False
    assert decisions[0].payload["blocked_by"] == "quality_gate"


def test_policy_allows_drag_release_even_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=False, score=0.25),
        [make_candidate("drag_release", RiskClass.MEDIUM)],
        {},
    )

    assert [decision.action for decision in decisions if decision.committed] == ["drag_release"]


def test_policy_requires_explicit_confirm_for_task_view_commit() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view_commit", RiskClass.HIGH)],
        {},
    )

    assert len(decisions) == 1
    assert decisions[0].committed is False
    assert decisions[0].payload["blocked_by"] == "explicit_confirm_required"


def test_policy_requires_explicit_confirm_for_task_view_open() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view", RiskClass.HIGH)],
        {},
    )

    assert len(decisions) == 1
    assert decisions[0].committed is False
    assert decisions[0].payload["blocked_by"] == "explicit_confirm_required"


def test_policy_requires_explicit_confirm_for_palm_swipe() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("swipe_left_palm", RiskClass.HIGH)],
        {},
    )

    assert len(decisions) == 1
    assert decisions[0].committed is False
    assert decisions[0].payload["blocked_by"] == "explicit_confirm_required"


def test_policy_allows_explicit_confirmed_task_view_commit() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view_commit", RiskClass.HIGH, explicit_confirm=1.0)],
        {},
    )

    assert [decision.action for decision in decisions if decision.committed] == ["task_view_commit"]


def test_policy_can_disable_explicit_confirm_requirement() -> None:
    policy = GesturePolicy(explicit_confirm_required=False)

    decisions = policy.evaluate(
        None,
        make_quality(ok=True),
        [make_candidate("task_view_commit", RiskClass.HIGH)],
        {},
    )

    assert [decision.action for decision in decisions if decision.committed] == ["task_view_commit"]


def test_policy_allows_task_view_cancel_when_quality_is_bad() -> None:
    policy = GesturePolicy()

    decisions = policy.evaluate(
        None,
        make_quality(ok=False, score=0.1),
        [make_candidate("task_view_cancel", RiskClass.HIGH)],
        {},
    )

    assert [decision.action for decision in decisions if decision.committed] == ["task_view_cancel"]


def test_policy_blocks_high_risk_during_cooldown() -> None:
    policy = GesturePolicy(high_risk_cooldown_ms=500, explicit_confirm_required=False)
    quality = make_quality(ok=True)

    first = policy.evaluate(
        None,
        quality,
        [make_candidate("task_view", RiskClass.HIGH)],
        {"now_ms": 1000},
    )
    second = policy.evaluate(
        None,
        quality,
        [make_candidate("task_view", RiskClass.HIGH)],
        {"now_ms": 1100},
    )

    assert [decision.action for decision in first if decision.committed] == ["task_view"]
    assert len(second) == 1
    assert second[0].committed is False
    assert second[0].payload["blocked_by"] == "cooldown"


def test_policy_records_blocked_reason_for_disabled_feature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        config_module,
        "ACTIVE_CONFIG",
        replace(
            config_module.ACTIVE_CONFIG,
            gesture_switches=replace(GestureSwitches(), win_d=False),
        ),
    )
    policy = GesturePolicy()

    decision = policy.decide_candidate(
        make_candidate("swipe_left_palm", RiskClass.HIGH),
        make_quality(ok=True),
        {"now_ms": 1000},
    )

    assert decision.committed is False
    assert decision.payload["blocked_by"] == "feature_disabled"
