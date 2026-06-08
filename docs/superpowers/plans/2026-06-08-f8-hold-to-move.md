# Right Ctrl Hold-to-Move Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a global `Right Ctrl` hold-to-move clutch so mouse movement becomes an explicit exclusive mode and no longer runs concurrently with click attempts.

**Architecture:** Keep the existing engagement, pointer, click, and grab detectors, but insert two new coordination layers: a global clutch input source for `Right Ctrl`, and a small movement-mode state machine that gates pointer output. Integrate both in `app.py`, suppress conflicting gesture channels while move mode is active, and expose state in the debug overlay.

**Tech Stack:** Python 3.11+, OpenCV, MediaPipe, PyAutoGUI, `pynput` for global keyboard listening, pytest

---

## File Map

- Create: `src/handmouse/clutch_input.py`
  - Global clutch state provider with a small interface that can be faked in tests.
- Create: `src/handmouse/move_mode.py`
  - `NEUTRAL / ARMED / ACTIVE` state machine for movement clutch behavior.
- Modify: `src/handmouse/app.py`
  - Wire clutch input, move mode, pointer gating, suppression of click/grab/shortcut during move active, and fix the current `_screen_size()` control-flow bug while touching lifecycle code.
- Modify: `src/handmouse/debug_view.py`
  - Show clutch state, move mode state, and move pose status.
- Modify: `src/handmouse/pyproject.toml`
  - Add `pynput` dependency.
- Modify: `tests/test_app.py`
  - Add integration-style loop tests for clutch gating and move-mode exclusivity.
- Create: `tests/test_move_mode.py`
  - Focused TDD coverage for the new movement mode state machine.
- Create: `tests/test_clutch_input.py`
  - Verify clutch input wrapper behavior without requiring a real global listener.

### Task 1: Add Move Mode State Machine

**Files:**
- Create: `src/handmouse/move_mode.py`
- Create: `tests/test_move_mode.py`

- [ ] **Step 1: Write the failing tests**

```python
from handmouse.move_mode import MoveModeConfig, MoveModeController, MoveModeState


def test_requires_stable_pose_before_becoming_active() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=150, pose_loss_grace_ms=80))

    first = controller.update(clutch_down=True, move_pose=True, now_ms=0)
    second = controller.update(clutch_down=True, move_pose=True, now_ms=100)
    third = controller.update(clutch_down=True, move_pose=True, now_ms=160)

    assert first.state is MoveModeState.ARMED
    assert second.state is MoveModeState.ARMED
    assert third.state is MoveModeState.ACTIVE


def test_clutch_release_exits_immediately() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=100, pose_loss_grace_ms=80))

    controller.update(clutch_down=True, move_pose=True, now_ms=0)
    controller.update(clutch_down=True, move_pose=True, now_ms=120)
    released = controller.update(clutch_down=False, move_pose=True, now_ms=121)

    assert released.state is MoveModeState.NEUTRAL
    assert released.movement_enabled is False


def test_brief_pose_loss_during_active_does_not_enable_other_modes() -> None:
    controller = MoveModeController(MoveModeConfig(arm_dwell_ms=100, pose_loss_grace_ms=80))

    controller.update(clutch_down=True, move_pose=True, now_ms=0)
    controller.update(clutch_down=True, move_pose=True, now_ms=120)
    lost = controller.update(clutch_down=True, move_pose=False, now_ms=150)

    assert lost.state is MoveModeState.ARMED
    assert lost.movement_enabled is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_move_mode.py`

Expected: `ModuleNotFoundError` or import failure for `handmouse.move_mode`

- [ ] **Step 3: Write the minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MoveModeState(Enum):
    NEUTRAL = auto()
    ARMED = auto()
    ACTIVE = auto()


@dataclass(frozen=True)
class MoveModeConfig:
    arm_dwell_ms: int = 150
    pose_loss_grace_ms: int = 80


@dataclass(frozen=True)
class MoveModeResult:
    state: MoveModeState
    movement_enabled: bool
    move_pose: bool
    clutch_down: bool


class MoveModeController:
    def __init__(self, config: MoveModeConfig) -> None:
        self.config = config
        self._state = MoveModeState.NEUTRAL
        self._armed_since_ms: int | None = None

    def update(self, *, clutch_down: bool, move_pose: bool, now_ms: int) -> MoveModeResult:
        if not clutch_down:
            self.reset()
            return MoveModeResult(MoveModeState.NEUTRAL, False, move_pose, clutch_down)

        if self._state is MoveModeState.NEUTRAL:
            if move_pose:
                self._state = MoveModeState.ARMED
                self._armed_since_ms = now_ms
            return MoveModeResult(self._state, False, move_pose, clutch_down)

        if self._state is MoveModeState.ARMED:
            if not move_pose:
                self._armed_since_ms = None
                self._state = MoveModeState.NEUTRAL
                return MoveModeResult(MoveModeState.NEUTRAL, False, move_pose, clutch_down)
            if self._armed_since_ms is None:
                self._armed_since_ms = now_ms
            if now_ms - self._armed_since_ms >= self.config.arm_dwell_ms:
                self._state = MoveModeState.ACTIVE
                return MoveModeResult(MoveModeState.ACTIVE, True, move_pose, clutch_down)
            return MoveModeResult(MoveModeState.ARMED, False, move_pose, clutch_down)

        if not move_pose:
            self._state = MoveModeState.ARMED
            self._armed_since_ms = now_ms
            return MoveModeResult(MoveModeState.ARMED, False, move_pose, clutch_down)

        return MoveModeResult(MoveModeState.ACTIVE, True, move_pose, clutch_down)

    def reset(self) -> None:
        self._state = MoveModeState.NEUTRAL
        self._armed_since_ms = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_move_mode.py`

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/test_move_mode.py src/handmouse/move_mode.py
git commit -m "feat: add move mode controller"
```

### Task 2: Add Global Right Ctrl Clutch Input Wrapper

**Files:**
- Create: `src/handmouse/clutch_input.py`
- Create: `tests/test_clutch_input.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing tests**

```python
from handmouse.clutch_input import ClutchSnapshot, ManualClutchInput


def test_manual_clutch_input_tracks_press_and_release() -> None:
    clutch = ManualClutchInput()

    clutch.set_pressed(True)
    first = clutch.snapshot()
    clutch.set_pressed(False)
    second = clutch.snapshot()

    assert first == ClutchSnapshot(clutch_down=True)
    assert second == ClutchSnapshot(clutch_down=False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_clutch_input.py`

Expected: import failure for `handmouse.clutch_input`

- [ ] **Step 3: Write the minimal implementation**

```python
from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class ClutchSnapshot:
    clutch_down: bool


class ManualClutchInput:
    def __init__(self) -> None:
        self._pressed = False

    def set_pressed(self, pressed: bool) -> None:
        self._pressed = pressed

    def snapshot(self) -> ClutchSnapshot:
        return ClutchSnapshot(clutch_down=self._pressed)

class GlobalClutchInput:
    def __init__(self, key_name: str = "ctrl_r") -> None:
        self._pressed = False
        self._lock = Lock()
        self._listener: Any | None = None

    def start(self) -> None:
        from pynput import keyboard

        def on_press(key: Any) -> None:
            if key == keyboard.Key.ctrl_r:
                with self._lock:
                    self._pressed = True

        def on_release(key: Any) -> None:
            if key == keyboard.Key.ctrl_r:
                with self._lock:
                    self._pressed = False

        self._listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def snapshot(self) -> ClutchSnapshot:
        with self._lock:
            return ClutchSnapshot(clutch_down=self._pressed)
```

- [ ] **Step 4: Update dependency declaration**

Add to `pyproject.toml` project dependencies:

```toml
"pynput>=1.7.7",
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_clutch_input.py`

Expected: `1 passed`

- [ ] **Step 6: Commit**

```bash
git add src/handmouse/clutch_input.py tests/test_clutch_input.py pyproject.toml
git commit -m "feat: add global clutch input"
```

### Task 3: Integrate Right Ctrl Clutch and Move Mode Into App Loop

**Files:**
- Modify: `src/handmouse/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing integration tests**

Add tests covering:

```python
def test_run_loop_moves_only_when_clutch_down_and_mode_active() -> None:
    ...
    assert mouse.moves == [ScreenDelta(12, 0)]


def test_run_loop_blocks_click_and_scroll_while_move_mode_active() -> None:
    ...
    assert mouse.clicks == 0
    assert shortcut.scrolled == []
    assert gesture.calls[0][0] is None
```

Also add a lifecycle test:

```python
def test_main_stops_clutch_input_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py -k "clutch or move_mode"`

Expected: failing assertions because app has no clutch integration yet

- [ ] **Step 3: Implement app wiring**

Modify `app.py` to:

- instantiate `GlobalClutchInput` in `main()`,
- start it before entering `_run_loop()`,
- stop it in `finally`,
- create a `MoveModeController`,
- pass clutch input and move mode into `_run_loop()`,
- fix `_screen_size()` so the `pyautogui.size()` call is reachable again,
- compute `move_pose` from landmarks using a dedicated helper such as `_is_move_pose()`,
- update move mode every frame,
- only call `pointer.update()` and `mouse.move_relative()` when `movement_enabled` is true,
- feed neutral input into gesture/grab/shortcut paths while move mode is active,
- keep existing failsafe shutdown behavior.

Representative integration sketch:

```python
clutch_snapshot = clutch_input.snapshot()
move_pose = _is_move_pose(hand_result.landmarks)
move_mode_result = move_mode.update(
    clutch_down=clutch_snapshot.clutch_down,
    move_pose=move_pose,
    now_ms=now_ms,
)

if move_mode_result.movement_enabled:
    delta = pointer.update(hand_result, now_ms)
    gesture_result = gesture.update(None, None, now_ms)
    grab_result = grab_scroll.update(None, now_ms)
    shortcut_detector.reset()
else:
    pointer.reset()
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py -k "clutch or move_mode"`

Expected: target tests pass

- [ ] **Step 5: Commit**

```bash
git add src/handmouse/app.py tests/test_app.py
git commit -m "feat: gate pointer movement behind clutch"
```

### Task 4: Add Debug Overlay Visibility for Clutch and Move Mode

**Files:**
- Modify: `src/handmouse/debug_view.py`
- Modify: `src/handmouse/app.py`
- Modify: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Add a lightweight test that verifies telemetry passed to `DebugView.draw()` includes clutch and move mode fields.

```python
def test_run_loop_passes_clutch_and_move_mode_telemetry() -> None:
    ...
    assert debug_view.last_telemetry.clutch_down is True
    assert debug_view.last_telemetry.move_mode == "ACTIVE"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest -q tests/test_app.py -k "telemetry"`

Expected: missing telemetry fields

- [ ] **Step 3: Implement telemetry updates**

Extend `DebugTelemetry` with:

```python
clutch_down: bool | None = None
move_mode: str | None = None
move_pose: bool | None = None
```

Update panel lines to show:

```python
f"Clutch: {'DOWN' if clutch_down else 'UP'}"
f"Move mode: {move_mode} pose={'yes' if move_pose else 'no'}"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest -q tests/test_app.py -k "telemetry"`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/handmouse/debug_view.py src/handmouse/app.py tests/test_app.py
git commit -m "feat: add clutch telemetry to debug overlay"
```

### Task 5: Full Verification

**Files:**
- Modify: `README.md` only if actual key behavior changes user instructions enough to be misleading

- [ ] **Step 1: Run focused test suites**

Run:

```bash
python -m pytest -q tests/test_move_mode.py tests/test_clutch_input.py tests/test_app.py
```

Expected: all pass

- [ ] **Step 2: Run the full suite**

Run:

```bash
python -m pytest -q
```

Expected: all tests pass

- [ ] **Step 3: Smoke-check the user-facing command path**

Run:

```bash
python -m handmouse.app
```

Expected: app starts, debug window opens, no immediate import error for `pynput`

- [ ] **Step 4: If README behavior is stale, update it**

Document:

- `Right Ctrl` hold-to-move,
- movement exclusivity,
- any remaining `m` / `q` semantics.

- [ ] **Step 5: Commit final polish**

```bash
git add README.md src/handmouse/*.py tests/*.py pyproject.toml
git commit -m "feat: implement Right Ctrl hold-to-move clutch"
```
