from handmouse.engagement import EngagementConfig, EngagementFSM, EngagementState


CONFIG = EngagementConfig(
    activation_hotkey="m",
    palm_hold_ms=200,
    cooldown_ms=100,
    missing_frames_to_idle=4,
    escape_hotkey="q",
)


def make_fsm() -> EngagementFSM:
    return EngagementFSM(CONFIG)


def test_initial_state_idle() -> None:
    fsm = make_fsm()

    assert fsm.state == EngagementState.IDLE


def test_hotkey_press_idle_to_armed() -> None:
    fsm = make_fsm()

    result = fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )

    assert result.state == EngagementState.ARMED
    assert result.is_active is False
    assert result.reason == "hotkey"
    assert fsm.state == EngagementState.ARMED


def test_palm_hold_200ms_idle_to_armed() -> None:
    fsm = make_fsm()

    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=True,
        palm_hold_ms=200,
        hand_missing=False,
        escape_requested=False,
        now_ms=200,
    )

    assert result.state == EngagementState.ARMED
    assert result.is_active is False
    assert result.reason == "palm_hold"


def test_palm_hold_short_does_not_arm() -> None:
    fsm = make_fsm()

    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=True,
        palm_hold_ms=100,
        hand_missing=False,
        escape_requested=False,
        now_ms=100,
    )

    assert result.state == EngagementState.IDLE
    assert result.is_active is False
    assert result.reason == "idle"


def test_armed_to_active_when_hand_visible() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    assert result.state == EngagementState.ACTIVE
    assert result.is_active is True
    assert result.reason == "active"


def test_active_to_cooldown_when_hand_missing_4_frames() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    result = None
    for index in range(4):
        result = fsm.update(
            hotkey_pressed=False,
            palm_visible=False,
            palm_hold_ms=0,
            hand_missing=True,
            escape_requested=False,
            now_ms=32 + index * 16,
        )

    assert result is not None
    assert result.state == EngagementState.COOLDOWN
    assert result.is_active is False
    assert result.reason == "missing"


def test_cooldown_to_idle_after_100ms() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=True,
        escape_requested=False,
        now_ms=32,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=True,
        escape_requested=False,
        now_ms=48,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=True,
        escape_requested=False,
        now_ms=64,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=True,
        escape_requested=False,
        now_ms=80,
    )

    still_cooldown = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=179,
    )
    done = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=180,
    )

    assert still_cooldown.state == EngagementState.COOLDOWN
    assert done.state == EngagementState.IDLE
    assert done.is_active is False
    assert done.reason == "cooldown_done"


def test_escape_requested_returns_to_idle_from_active() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=True,
        now_ms=32,
    )

    assert result.state == EngagementState.IDLE
    assert result.is_active is False
    assert result.reason == "escape"


def test_force_idle_immediate() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    fsm.force_idle()

    assert fsm.state == EngagementState.IDLE

    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    assert result.state == EngagementState.IDLE
    assert result.is_active is False


def test_toggle_semantics_hotkey_press_idle_again() -> None:
    fsm = make_fsm()

    first = fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    second = fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    assert first.state == EngagementState.ARMED
    assert second.state == EngagementState.IDLE
    assert second.is_active is False
    assert second.reason == "hotkey"


def test_reset_clears_state() -> None:
    fsm = make_fsm()

    fsm.update(
        hotkey_pressed=True,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=0,
    )
    fsm.reset()

    assert fsm.state == EngagementState.IDLE

    result = fsm.update(
        hotkey_pressed=False,
        palm_visible=False,
        palm_hold_ms=0,
        hand_missing=False,
        escape_requested=False,
        now_ms=16,
    )

    assert result.state == EngagementState.IDLE
    assert result.is_active is False
    assert result.reason == "idle"
