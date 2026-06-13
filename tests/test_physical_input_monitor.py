from handmouse.physical_input_monitor import (
    LLKHF_INJECTED,
    LLMHF_INJECTED,
    PhysicalInputMonitor,
    _is_injected,
)


def test_is_recent_false_when_no_input() -> None:
    m = PhysicalInputMonitor()
    assert m.last_physical_input_ms is None
    assert m.is_recent(now_ms=5000, grace_ms=800) is False


def test_is_recent_true_within_grace() -> None:
    m = PhysicalInputMonitor()
    m._last_ms = 1000
    assert m.is_recent(now_ms=1500, grace_ms=800) is True


def test_is_recent_false_after_grace() -> None:
    m = PhysicalInputMonitor()
    m._last_ms = 1000
    assert m.is_recent(now_ms=2000, grace_ms=800) is False


def test_is_recent_grace_boundary_is_exclusive() -> None:
    m = PhysicalInputMonitor()
    m._last_ms = 1000
    assert m.is_recent(now_ms=1800, grace_ms=800) is False


def test_is_recent_true_for_mark_just_after_now() -> None:
    # The monitor runs on a listener thread; a mark can land microseconds after
    # now_ms was captured, giving a small negative diff — still "recent".
    m = PhysicalInputMonitor()
    m._last_ms = 1600
    assert m.is_recent(now_ms=1500, grace_ms=800) is True


def test_mark_sets_recent() -> None:
    m = PhysicalInputMonitor()
    m._mark()
    last = m.last_physical_input_ms
    assert last is not None
    assert m.is_recent(now_ms=last, grace_ms=800) is True


def test_stop_is_safe_when_never_started() -> None:
    m = PhysicalInputMonitor()
    m.stop()  # must not raise


def test_injected_flag_detection() -> None:
    # Synthetic (HandMouse's own) events carry the injected bit and must be ignored.
    assert _is_injected(LLKHF_INJECTED, LLKHF_INJECTED) is True
    assert _is_injected(LLMHF_INJECTED, LLMHF_INJECTED) is True
    assert _is_injected(0x00, LLKHF_INJECTED) is False
    assert _is_injected(0x00, LLMHF_INJECTED) is False
    # Real hardware events have the bit clear even if other flags are set.
    assert _is_injected(0x20, LLKHF_INJECTED) is False
    # Malformed/missing flags must not crash and count as not-injected (physical).
    assert _is_injected(None, LLMHF_INJECTED) is False
    assert _is_injected("bogus", LLMHF_INJECTED) is False
