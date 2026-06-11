"""Tests for the open-palm heuristic used to drive palm_swipe (Win+D) gestures."""
from __future__ import annotations

from types import SimpleNamespace
from handmouse.app import _is_palm_open


def _lm(x: float, y: float) -> SimpleNamespace:
    return SimpleNamespace(x=x, y=y)


def _make_landmarks(
    index_tip_ratio: float,
    middle_tip_ratio: float = 2.0,
    ring_tip_ratio: float = 2.0,
    pinky_tip_ratio: float = 2.0,
) -> list[SimpleNamespace]:
    """Build 21 landmarks with palm-center at (0.5, 0.5).

    Each MCP is placed at a fixed distance from palm-center; each fingertip is
    placed at `*_tip_ratio` times that distance so that `tip_d / mcp_d` equals
    the requested ratio.  Only the y-axis is used to vary the ratio (palm-center
    is also on the y=0.5 line, so vertical placement yields a clean Euclidean
    distance computation).
    """
    # 21 landmarks, all set to palm-center first.
    landmarks = [_lm(0.5, 0.5) for _ in range(21)]

    # Place palm-center at (0.5, 0.5).  Each MCP sits 0.1 above palm-center so
    # mcp_d (Euclidean distance to palm-center) is 0.1 for every MCP.
    mcp_distance = 0.1
    # Index MCP (5), Middle MCP (9), Ring MCP (13), Pinky MCP (17) all at y = 0.4
    for mcp_idx in (5, 9, 13, 17):
        landmarks[mcp_idx] = _lm(0.5, 0.5 - mcp_distance)

    # Wrist (0) is below palm-center, doesn't affect ratio.
    landmarks[0] = _lm(0.5, 0.7)

    # Fingertips are above their MCPs (lower y value).  Set y = 0.5 - mcp_distance * ratio
    def _tip(idx: int, ratio: float) -> None:
        landmarks[idx] = _lm(0.5, 0.5 - mcp_distance * ratio)

    _tip(8, index_tip_ratio)
    _tip(12, middle_tip_ratio)
    _tip(16, ring_tip_ratio)
    _tip(20, pinky_tip_ratio)

    return landmarks


def test_palm_open_rejects_mostly_closed_hand() -> None:
    """When all fingertips are closer to palm-center than their MCPs, _is_palm_open is False."""
    landmarks = _make_landmarks(
        index_tip_ratio=0.8,
        middle_tip_ratio=0.8,
        ring_tip_ratio=0.8,
        pinky_tip_ratio=0.8,
    )
    assert _is_palm_open(landmarks) is False


def test_palm_open_accepts_clear_open_palm() -> None:
    """When all fingertips are well beyond their MCPs, _is_palm_open is True."""
    landmarks = _make_landmarks(
        index_tip_ratio=1.5,
        middle_tip_ratio=1.5,
        ring_tip_ratio=1.5,
        pinky_tip_ratio=1.5,
    )
    assert _is_palm_open(landmarks) is True


def test_palm_open_threshold_accepts_tip_at_mcp_distance() -> None:
    """With threshold lowered to 1.0, fingers whose tip/MCP ratio sits between
    1.0 and 1.1 (e.g. 1.05) now count as 'extended'.  Here we have two fingers
    at 1.05 and two well-extended:
      - Old threshold (1.1): only the two well-extended fingers count → extended=2 → False
      - New threshold (1.0): all four fingers count → extended=4 → True
    """
    landmarks = _make_landmarks(
        index_tip_ratio=1.05,
        middle_tip_ratio=1.05,
        ring_tip_ratio=1.5,
        pinky_tip_ratio=1.5,
    )
    assert _is_palm_open(landmarks) is True


def test_palm_open_threshold_still_rejects_ratio_below_one() -> None:
    """A tip closer to palm-center than the MCP (ratio<1.0) must still not
    count as extended; we need at least 3 fingers extended for a palm."""
    # Only two fingers extended; the other two are below the threshold.
    landmarks = _make_landmarks(
        index_tip_ratio=0.9,
        middle_tip_ratio=1.5,
        ring_tip_ratio=1.5,
        pinky_tip_ratio=0.9,
    )
    assert _is_palm_open(landmarks) is False


def test_palm_open_returns_false_for_missing_landmarks() -> None:
    assert _is_palm_open(None) is False
    assert _is_palm_open([]) is False
