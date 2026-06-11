# HandMouse Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining production-grade hardening work so HandMouse consistently separates intent from side effects, preserves 3D tracking data, blocks unsafe gestures under poor quality, and produces replayable telemetry.

**Architecture:** Keep the current `HandObservation -> TrackingQualityGate -> Detectors -> GesturePolicy -> ActionRouter` backbone, but finish the missing state and data plumbing. The remaining work is mostly correctness hardening, not feature expansion: make policy stateful, make telemetry first-class, propagate real 3D/world landmarks through the pipeline, and validate mirror/handedness geometry with deterministic fixtures.

**Tech Stack:** Python 3.13, pytest, MediaPipe Tasks hand landmarks, PyAutoGUI, YAML config, NDJSON telemetry.

---

## File Map

- Modify: `src/handmouse/tracking/quality_gate.py`
  - Expand quality scoring and expose stronger session-facing signals.
- Modify: `src/handmouse/policy/gesture_policy.py`
  - Add stateful gating, blocked reasons, cooldowns, and explicit-confirm semantics.
- Modify: `src/handmouse/actions/windows_backend.py`
  - Consume richer intents and keep OS side effects aligned with policy state.
- Modify: `src/handmouse/app.py`
  - Make telemetry writer first-class, pass session state, and remove remaining legacy glue.
- Modify: `src/handmouse/shortcut_detector.py`
  - Tighten palm-swipe semantics and avoid accidental high-risk dispatch.
- Modify: `src/handmouse/grab_scroll_detector.py`
  - Classify scroll as medium-risk under unstable tracking and expose measurements for policy.
- Modify: `src/handmouse/hand_tracker.py`
  - Preserve MediaPipe image/world landmark fidelity and expose enough metadata for downstream geometry.
- Modify: `src/handmouse/coordinate_mapper.py`
  - Centralize mirrored/physical handedness semantics and document the contract in code.
- Modify: `src/handmouse/config/__init__.py`
  - Add config defaults for schema version and production-hardening thresholds.
- Modify: `src/handmouse/config/schema.py`
  - Parse and validate new hardening settings.
- Create: `src/handmouse/telemetry/schema.py`
  - Shared typed event builders for frame, candidate, decision, and dispatch telemetry.
- Create: `src/handmouse/replay_runner.py`
  - Offline replay harness that consumes telemetry and asserts gesture outcomes.
- Create: `tests/test_quality_gate.py`
  - Quality scoring and stale/stability threshold coverage.
- Modify: `tests/test_gesture_policy.py`
  - Add stateful policy/cooldown/blocked-reason assertions.
- Modify: `tests/test_shortcut_detector.py`
  - Add palm-swipe and win+d gating expectations.
- Modify: `tests/test_grab_scroll_detector.py`
  - Add unstable/low-quality behavior expectations.
- Modify: `tests/test_hand_tracker.py`
  - Assert image z and world landmark fidelity.
- Modify: `tests/test_app.py`
  - Assert telemetry schema, session state flow, and explicit blocked reasons.
- Create: `tests/test_replay_runner.py`
  - Replay harness regression coverage.
- Create: `docs/telemetry.md`
  - Event schema and replay workflow reference.

### Task 1: Strengthen Tracking Quality Signals

**Files:**
- Modify: `src/handmouse/tracking/quality_gate.py`
- Create: `tests/test_quality_gate.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing quality gate tests**

```python
from handmouse.tracking.observation import HandObservation, Point3
from handmouse.tracking.quality_gate import TrackingQualityGate


def _obs(*, stale_ms: int = 0, span: float = 0.18, score: float = 0.99) -> HandObservation:
    points = [Point3(0.5, 0.5, 0.01)] * 21
    points[5] = Point3(0.50, 0.50, 0.01)
    points[17] = Point3(0.50 + span, 0.60, 0.01)
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
    result = gate.update(_obs(stale_ms=120, span=0.01), 1920, 1080)
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_quality_gate.py tests/test_app.py -v`
Expected: FAIL because `TrackingQualityGate` still returns coarse `score=1.0/0.5` and does not expose enough signal for downstream policy.

- [ ] **Step 3: Implement richer quality scoring**

```python
class TrackingQualityGate:
    def update(self, obs: HandObservation | None, screen_width: int, screen_height: int) -> TrackingQuality:
        ...
        penalties = 0.0
        if obs.stale_ms > self.max_stale_ms:
            reasons.append("stale")
            penalties += 0.45
        if self._stable_frames < self.min_stable_frames:
            reasons.append("unstable")
            penalties += 0.30
        if palm_span_px < self.min_palm_span_px:
            reasons.append("palm_too_small")
            penalties += 0.25
        if not handedness_ok:
            reasons.append("handedness_uncertain")
            penalties += 0.20

        score = max(0.0, 1.0 - penalties)
        ok = score >= 0.75 and not reasons
        return TrackingQuality(
            ok=ok,
            score=score,
            reasons=tuple(reasons),
            palm_span_px=palm_span_px,
            handedness_ok=handedness_ok,
            stable_frames=self._stable_frames,
            lost_frames=0,
        )
```

- [ ] **Step 4: Add app-level assertions that telemetry includes quality reasons**

```python
def test_run_loop_logs_quality_reasons(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
    decisions = [payload for event_name, payload in events if event_name == "gesture_decision"]
    assert decisions[0]["quality_reasons"] == ["unstable"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_quality_gate.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/tracking/quality_gate.py tests/test_quality_gate.py tests/test_app.py
git commit -m "feat(quality): strengthen tracking quality scoring"
```

### Task 2: Make GesturePolicy Stateful and Explainable

**Files:**
- Modify: `src/handmouse/policy/gesture_policy.py`
- Modify: `src/handmouse/app.py`
- Modify: `tests/test_gesture_policy.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing policy state tests**

```python
def test_policy_blocks_high_risk_during_cooldown() -> None:
    policy = GesturePolicy(high_risk_cooldown_ms=500)
    quality = make_quality(ok=True)
    first = policy.evaluate(None, quality, [make_candidate("task_view", RiskClass.HIGH)], {"now_ms": 1000})
    second = policy.evaluate(None, quality, [make_candidate("task_view", RiskClass.HIGH)], {"now_ms": 1100})
    assert [intent.action for intent in first] == ["task_view"]
    assert second == []


def test_policy_records_blocked_reason_for_disabled_feature() -> None:
    policy = GesturePolicy()
    decision = policy.decide_candidate(make_candidate("swipe_left_palm", RiskClass.HIGH), make_quality(ok=True), {"now_ms": 1000})
    assert decision.committed is False
    assert decision.payload["blocked_by"] == "feature_disabled"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_gesture_policy.py tests/test_app.py -v`
Expected: FAIL because policy is stateless and does not return structured blocked reasons.

- [ ] **Step 3: Refactor policy to return committed and blocked decisions**

```python
@dataclass(frozen=True)
class GestureDecision:
    action: str
    risk: RiskClass
    detector: str
    committed: bool
    payload: dict[str, Any] = field(default_factory=dict)


class GesturePolicy:
    def __init__(self, high_risk_cooldown_ms: int = 500) -> None:
        self.high_risk_cooldown_ms = high_risk_cooldown_ms
        self._last_high_risk_ms = -1

    def evaluate(..., session_state: dict[str, Any]) -> list[GestureDecision]:
        now_ms = int(session_state.get("now_ms", 0))
        decisions: list[GestureDecision] = []
        for candidate in candidates:
            blocked_by = self._blocked_reason(candidate, quality, now_ms)
            committed = blocked_by is None
            if committed and candidate.risk == RiskClass.HIGH:
                self._last_high_risk_ms = now_ms
            decisions.append(
                GestureDecision(
                    action=candidate.gesture,
                    risk=candidate.risk,
                    detector=candidate.detector,
                    committed=committed,
                    payload={**candidate.measurements, "blocked_by": blocked_by},
                )
            )
        return decisions
```

- [ ] **Step 4: Update app to log decisions directly instead of reconstructing blocked state**

```python
decisions = policy.evaluate(obs, quality, candidates, {"now_ms": now_ms, "task_view_open": last_task_view_ms > 0})
intents = [GestureIntent(...decision fields...) for decision in decisions if decision.committed]
for decision in decisions:
    log_event("gesture_decision", {
        "ts_ms": now_ms,
        "action": decision.action,
        "risk": decision.risk.value,
        "detector": decision.detector,
        "committed": decision.committed,
        "blocked_by": decision.payload.get("blocked_by"),
        "quality_reasons": list(quality.reasons),
    })
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_gesture_policy.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/policy/gesture_policy.py src/handmouse/app.py tests/test_gesture_policy.py tests/test_app.py
git commit -m "feat(policy): add stateful gesture gating and blocked reasons"
```

### Task 3: Make Telemetry a First-Class Schema

**Files:**
- Create: `src/handmouse/telemetry/schema.py`
- Modify: `src/handmouse/telemetry/writer.py`
- Modify: `src/handmouse/app.py`
- Create: `docs/telemetry.md`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing telemetry schema tests**

```python
from handmouse.telemetry.schema import build_frame_sample


def test_frame_sample_schema_contains_world_z_and_quality() -> None:
    payload = build_frame_sample(
        ts_ms=1000,
        frame_age_ms=12,
        pointer_dx=0.0,
        pointer_dy=0.0,
        landmarks=[[0.5, 0.5, 0.01]],
        world_landmarks=[[0.1, 0.2, 0.3]],
        quality_score=0.91,
        quality_reasons=("stable",),
    )
    assert payload["schema_version"] == 2
    assert payload["world_landmarks"][0] == [0.1, 0.2, 0.3]
    assert payload["quality_score"] == 0.91
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL because there is no shared telemetry schema builder and the frame payload is assembled inline.

- [ ] **Step 3: Implement typed telemetry builders**

```python
def build_frame_sample(..., quality_score: float, quality_reasons: tuple[str, ...]) -> dict[str, Any]:
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
    }
```

- [ ] **Step 4: Route all app telemetry through schema builders**

```python
from handmouse.telemetry.schema import build_frame_sample, build_gesture_candidate, build_gesture_decision

log_event("frame_sample", build_frame_sample(
    ts_ms=now_ms,
    frame_age_ms=frame_age_ms,
    pointer_dx=dx,
    pointer_dy=dy,
    landmarks=[[lm.x, lm.y, lm.z] for lm in obs.image_landmarks] if obs else [],
    world_landmarks=[[lm.x, lm.y, lm.z] for lm in hand_result.world_landmarks] if hand_result and hand_result.world_landmarks else None,
    quality_score=quality.score,
    quality_reasons=quality.reasons,
))
```

- [ ] **Step 5: Document the telemetry contract**

```markdown
# HandMouse Telemetry

- `schema_version=2` is required for all new recordings.
- `frame_sample` includes image landmarks as `[x, y, z]`.
- `gesture_decision` is emitted for both committed and blocked candidates.
- `action_dispatch` records the final OS side effect or policy-level skip.
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/handmouse/telemetry/schema.py src/handmouse/telemetry/writer.py src/handmouse/app.py docs/telemetry.md tests/test_app.py
git commit -m "feat(telemetry): formalize schema and app logging"
```

### Task 4: Finish 3D and World-Landmark Propagation

**Files:**
- Modify: `src/handmouse/hand_tracker.py`
- Modify: `src/handmouse/coordinate_mapper.py`
- Modify: `src/handmouse/app.py`
- Modify: `tests/test_hand_tracker.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write failing world-landmark fidelity tests**

```python
def test_convert_result_preserves_image_and_world_z() -> None:
    tracker = HandTracker.__new__(HandTracker)
    result = SimpleNamespace(
        hand_landmarks=[[SimpleNamespace(x=0.1, y=0.2, z=-0.03) for _ in range(21)]],
        hand_world_landmarks=[[SimpleNamespace(x=0.4, y=0.5, z=0.6) for _ in range(21)]],
        handedness=[[SimpleNamespace(category_name="Left", score=0.99)]],
    )
    output = tracker._convert_result(result)
    assert output.raw_landmarks[0].z == -0.03
    assert output.world_landmarks[0].z == 0.6
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_hand_tracker.py tests/test_app.py -v`
Expected: FAIL if any path drops image z, world z, or reintroduces 2D-only assumptions.

- [ ] **Step 3: Centralize landmark conversion helpers**

```python
def _point3_list(raw_landmarks: Any) -> list[Point3]:
    return [
        Point3(
            x=float(getattr(lm, "x", 0.0)),
            y=float(getattr(lm, "y", 0.0)),
            z=float(getattr(lm, "z", 0.0)),
        )
        for lm in raw_landmarks
    ]
```

- [ ] **Step 4: Keep coordinate mapping explicit about mirrored image space vs physical semantics**

```python
def unify_hand_result(raw_result: HandTrackingResult, input_is_mirrored: bool) -> HandTrackingResult:
    # Image landmarks stay in unified image space; world landmarks are passed through untouched.
    unified_landmarks = [FramePoint(x=lm.x, y=lm.y) for lm in raw_result.landmarks]
    return HandTrackingResult(
        landmarks=unified_landmarks,
        thumb_tip=...,
        index_tip=...,
        raw_landmarks=raw_result.raw_landmarks,
        world_landmarks=raw_result.world_landmarks,
        handedness_label=raw_result.handedness_label,
        handedness_confidence=raw_result.handedness_confidence,
    )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_hand_tracker.py tests/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/hand_tracker.py src/handmouse/coordinate_mapper.py src/handmouse/app.py tests/test_hand_tracker.py tests/test_app.py
git commit -m "feat(tracking): preserve full 3d landmark fidelity"
```

### Task 5: Harden Palm Swipe and Win+D Routing

**Files:**
- Modify: `src/handmouse/shortcut_detector.py`
- Modify: `src/handmouse/actions/windows_backend.py`
- Modify: `tests/test_shortcut_detector.py`
- Modify: `tests/test_gesture_policy.py`

- [ ] **Step 1: Write failing palm-swipe tests**

```python
def test_palm_swipe_requires_open_palm_history_and_release_window() -> None:
    detector = make_detector()
    detector.update(make_obs(), now_ms=0, point=FramePoint(0.5, 0.5), palm_open=False)
    result = detector.update(make_obs(), now_ms=100, point=FramePoint(0.1, 0.5), palm_open=False)
    assert [c.gesture for c in result] == ["swipe_left"]


def test_win_d_disabled_blocks_palm_swipe_at_policy() -> None:
    ...
    assert intents == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_shortcut_detector.py tests/test_gesture_policy.py -v`
Expected: FAIL if palm swipes still piggyback on loose historical palm-open state.

- [ ] **Step 3: Tighten palm-swipe classification**

```python
if self._palm_was_open and elapsed_ms >= self.config.min_palm_hold_ms:
    if action == ShortcutAction.SWIPE_LEFT:
        action = ShortcutAction.SWIPE_LEFT_PALM
```

- [ ] **Step 4: Keep router side effects narrow**

```python
if intent.action.startswith("swipe_"):
    mapped_action = action_map.get(intent.action)
    if mapped_action is not None:
        self.shortcut.execute(mapped_action)
        executed = True
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_shortcut_detector.py tests/test_gesture_policy.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/shortcut_detector.py src/handmouse/actions/windows_backend.py tests/test_shortcut_detector.py tests/test_gesture_policy.py
git commit -m "fix(shortcuts): harden palm swipe and win+d routing"
```

### Task 6: Build an Actual Replay Harness

**Files:**
- Create: `src/handmouse/replay_runner.py`
- Create: `tests/test_replay_runner.py`
- Modify: `tests/test_regression_replay.py`
- Modify: `docs/telemetry.md`

- [ ] **Step 1: Write the failing replay harness test**

```python
from handmouse.replay_runner import ReplayRunner


def test_replay_runner_counts_blocked_and_committed_decisions(tmp_path) -> None:
    path = tmp_path / "session.ndjson"
    path.write_text(
        '{"event":"gesture_decision","action":"task_view","committed":false,"blocked_by":"quality_gate"}\n'
        '{"event":"gesture_decision","action":"click_left","committed":true}\n',
        encoding="utf-8",
    )
    report = ReplayRunner(path).run()
    assert report["committed"]["click_left"] == 1
    assert report["blocked"]["task_view"]["quality_gate"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_replay_runner.py tests/test_regression_replay.py -v`
Expected: FAIL because there is no executable replay harness yet.

- [ ] **Step 3: Implement the replay runner**

```python
class ReplayRunner:
    def __init__(self, telemetry_path: Path) -> None:
        self.telemetry_path = telemetry_path

    def run(self) -> dict[str, Any]:
        committed: Counter[str] = Counter()
        blocked: dict[str, Counter[str]] = defaultdict(Counter)
        for line in self.telemetry_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            if record.get("event") != "gesture_decision":
                continue
            if record.get("committed"):
                committed[record["action"]] += 1
            else:
                blocked[record["action"]][record.get("blocked_by", "unknown")] += 1
        return {"committed": dict(committed), "blocked": {k: dict(v) for k, v in blocked.items()}}
```

- [ ] **Step 4: Update regression replay tests to consume the harness instead of hand-rolled assertions**

```python
def test_regression_click_flow(...):
    report = run_pipeline_simulation(series)
    assert report["committed"]["click_left"] == 1
    assert report["committed"].get("drag_hold", 0) == 0
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_replay_runner.py tests/test_regression_replay.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/replay_runner.py tests/test_replay_runner.py tests/test_regression_replay.py docs/telemetry.md
git commit -m "feat(replay): add executable telemetry replay harness"
```

### Task 7: Lock Down Mirror and Palm-Facing Semantics

**Files:**
- Modify: `src/handmouse/app.py`
- Modify: `src/handmouse/coordinate_mapper.py`
- Modify: `tests/test_app.py`
- Modify: `docs/telemetry.md`

- [ ] **Step 1: Write failing mirror-semantics tests**

```python
def test_palm_facing_rejects_back_of_left_hand() -> None:
    assert _is_palm_facing_camera(make_back_of_hand_landmarks("Left"), "Left") is False


def test_coordinate_mapper_preserves_physical_handedness_labels() -> None:
    result = unify_hand_result(raw_result, input_is_mirrored=False)
    assert result.handedness_label == "Right"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL if any hand-orientation assumption is still implicit or undocumented.

- [ ] **Step 3: Normalize the code comments and debug metrics**

```python
# Unified image-space contract:
# - `landmarks` use image coordinates with x increasing toward the user's physical right.
# - `raw_landmarks` retain MediaPipe depth (`z`) for image-space geometry.
# - `world_landmarks` stay in MediaPipe world coordinates and are never mirrored.
```

- [ ] **Step 4: Add back-of-hand fixture coverage**

```python
def make_back_of_hand_landmarks(handedness: str) -> list[FramePoint]:
    ...
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/app.py src/handmouse/coordinate_mapper.py tests/test_app.py docs/telemetry.md
git commit -m "test(geometry): lock mirror and palm-facing semantics"
```

### Task 8: Finish Config Hardening and Rollout Readiness

**Files:**
- Modify: `src/handmouse/config/__init__.py`
- Modify: `src/handmouse/config/schema.py`
- Modify: `tests/test_config.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing config validation tests**

```python
def test_config_schema_version_defaults_to_v2() -> None:
    config = dict_to_app_config({})
    assert config.schema_version == 2


def test_invalid_high_risk_cooldown_is_rejected() -> None:
    with pytest.raises(ValueError):
        dict_to_app_config({"policy": {"high_risk_cooldown_ms": -1}})
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL because config schema versioning and hardening thresholds are not validated yet.

- [ ] **Step 3: Add explicit config sections**

```python
@dataclass(frozen=True)
class PolicyConfig:
    high_risk_cooldown_ms: int = 500
    explicit_confirm_required: bool = True


@dataclass(frozen=True)
class AppConfig:
    ...
    schema_version: int = 2
    policy: PolicyConfig = PolicyConfig()
```

- [ ] **Step 4: Document the rollout defaults**

```markdown
- `gesture_switches.win_d` defaults to `true`, but palm swipes now require open-palm history and quality OK.
- `policy.high_risk_cooldown_ms=500`
- `schema_version=2` enables replay-grade telemetry.
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/handmouse/config/__init__.py src/handmouse/config/schema.py tests/test_config.py README.md
git commit -m "feat(config): validate hardening policy defaults"
```

## Self-Review

- Spec coverage:
  - `GesturePolicy` still too thin: covered by Task 2.
  - TelemetryWriter not truly integrated as a schema: covered by Task 3.
  - Real `z` / `world_landmarks` propagation: covered by Task 4.
  - `Win+D` and palm swipe risk semantics: covered by Task 5.
  - Replay harness still missing: covered by Task 6.
  - Mirror / handedness / palm-facing uncertainty: covered by Task 7.
  - Config schema version and rollout validation: covered by Task 8.
- Placeholder scan:
  - No `TODO`, `TBD`, or unnamed validation steps remain.
- Type consistency:
  - `GestureDecision`, `PolicyConfig`, and replay report keys are referenced consistently across all tasks.

Plan complete and saved to `docs/superpowers/plans/2026-06-12-handmouse-production-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
