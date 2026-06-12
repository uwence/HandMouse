from handmouse.bimanual_gate import BimanualGate, BimanualGateState
from handmouse.tracking.observation import HandObservation, Point3


def _obs(palm_open: bool) -> HandObservation:
    lm = [Point3(0.5, 0.5, 0.0)] * 21
    lm[0] = Point3(0.5, 0.8, 0.0)
    for i in (5, 9, 13, 17):
        lm[i] = Point3(0.5, 0.6, 0.0)
    if palm_open:
        for tip_i in (8, 12, 16, 20):
            lm[tip_i] = Point3(0.5, 0.1, 0.0)  # extended
    else:
        for tip_i in (8, 12, 16, 20):
            lm[tip_i] = Point3(0.5, 0.62, 0.0)  # curled (tip_d/mcp_d ≈ 0.5 < 1.10)
    return HandObservation(
        frame_id=1, ts_ms=0, image_landmarks=lm, world_landmarks=None,
        handedness_label="Left", handedness_score=0.9,
        raw_result=None, stale_ms=0, camera_space="mirrored",
    )


OPEN = _obs(palm_open=True)
FIST = _obs(palm_open=False)


def _gate(open_hold_ms: int = 250) -> BimanualGate:
    return BimanualGate(open_hold_ms=open_hold_ms, open_stable_frames=3,
                        suspend_grace_ms=150, idle_grace_ms=500)


def test_idle_with_no_hands():
    g = _gate()
    r = g.update(mode_obs=None, pointer_obs=None, now_ms=0)
    assert r.state == BimanualGateState.IDLE
    assert r.gate_active is False


def test_transitions_to_armed_after_hold():
    g = _gate(open_hold_ms=250)
    for t in range(0, 300, 16):
        r = g.update(mode_obs=OPEN, pointer_obs=None, now_ms=t)
    assert r.state == BimanualGateState.ARMED


def test_stays_idle_before_hold_time():
    g = _gate(open_hold_ms=250)
    r = g.update(mode_obs=OPEN, pointer_obs=None, now_ms=0)
    assert r.state == BimanualGateState.IDLE


def test_armed_to_active_when_pointer_present():
    g = _gate(open_hold_ms=0)  # arm immediately (bypasses stable_frames)
    g.update(mode_obs=OPEN, pointer_obs=None, now_ms=0)  # → ARMED
    r = g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=16)
    assert r.state == BimanualGateState.ACTIVE
    assert r.gate_active is True


def test_active_suspends_when_mode_hand_lost():
    g = _gate(open_hold_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=16)  # ACTIVE
    # Mode hand gone for > 150ms since last seen at t=16
    r = g.update(mode_obs=None, pointer_obs=OPEN, now_ms=200)
    assert r.state == BimanualGateState.SUSPENDED
    assert r.gate_active is False


def test_suspended_recovers_when_mode_returns():
    g = _gate(open_hold_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=16)   # ACTIVE
    g.update(mode_obs=None, pointer_obs=OPEN, now_ms=200)  # SUSPENDED
    r = g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=250)
    assert r.state == BimanualGateState.ACTIVE


def test_suspended_to_idle_after_idle_grace():
    g = _gate(open_hold_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=16)   # ACTIVE
    g.update(mode_obs=None, pointer_obs=OPEN, now_ms=200)  # SUSPENDED
    r = g.update(mode_obs=None, pointer_obs=OPEN, now_ms=800)
    assert r.state == BimanualGateState.IDLE


def test_fist_sets_mode_is_secondary():
    g = _gate(open_hold_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=OPEN, now_ms=16)   # ACTIVE
    r = g.update(mode_obs=FIST, pointer_obs=OPEN, now_ms=32)
    assert r.gate_active is True
    assert r.mode_is_secondary is True


def test_idle_to_armed_resets_when_mode_hand_closes():
    g = _gate(open_hold_ms=0)
    g.update(mode_obs=OPEN, pointer_obs=None, now_ms=0)    # ARMED
    r = g.update(mode_obs=FIST, pointer_obs=None, now_ms=16)
    assert r.state == BimanualGateState.IDLE
