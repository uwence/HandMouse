# HandMouse v2

Windows-native Python prototype for controlling the mouse with webcam-based hand gestures. Single-hand, relative-pointer, release-to-commit pinch, explicit activation state.

## What changed in v2

| | v1 | v2 |
|---|---|---|
| Default pointer mode | absolute (or grab-scroll only) | **relative + adaptive gain + depth compensation** |
| Pinch semantics | hold 120ms then click | **release-to-commit** (double threshold 0.05 / 0.075) |
| Activation | "in frame = controlling" | **explicit**: IDLE / ARMED / ACTIVE / COOLDOWN FSM |
| MediaPipe mode | IMAGE + detect() | **VIDEO + detect_for_video(ms)** (tracking reuse) |
| Camera | 1280×720 default | **640×480**, DSHOW→MSMF→ANY, buffer=1 |
| Hand pose errors | ignored | palm-open required for engagement |

76/76 tests pass. See `docs/research/handmouse-v2-design.md` for the design rationale.

## Windows Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Or, if you already have the deps installed in a global venv (e.g. Hermes venv at `C:\Users\uwenc\.hermes\hermes-agent\venv`), just use that interpreter directly.

## Run

```powershell
python -m handmouse.app
```

First run downloads the MediaPipe hand landmarker model (~7.5 MB) to `%USERPROFILE%\.handmouse\models\hand_landmarker.task`. To pre-place it:

```powershell
$env:HANDMOUSE_MODEL_PATH = "C:\path\to\hand_landmarker.task"
```

## Keyboard controls

| Key | Action |
|---|---|
| `m` | Toggle ACTIVE / IDLE (engage or disengage mouse control) |
| `q` | Quit immediately |

## State machine

```
[IDLE]                                  start, or after 4 missing frames
   | m pressed, or palm open held 200ms
   v
[ARMED]
   | hand landmarks stable (one frame)
   v
[ACTIVE]                                 real mouse control ON
   | 4 consecutive frames with no hand   (COOLDOWN 100ms then back to IDLE)
   | q pressed                           (immediate exit)
   | m pressed                           (back to IDLE)
   v
[COOLDOWN] -> [IDLE]
```

`ACTIVE` is the only state where pointer / pinch / grab / swipe actually inject events into the OS. In every other state the debug overlay still draws, but no mouse / scroll / keyboard action is emitted.

## Hand gestures

You can use **either** keyboard activation (`m`) **or** palm-show activation (open palm held for ~200ms), **or both**. The FSM `OR`s them: any one of the two trigger paths engages ACTIVE.

### 1. Pointer movement (active in ACTIVE)

- **Control point**: index fingertip
- **Reference frame**: camera frame, with a default control region of 12%–88% horizontal × 10%–90% vertical (the orange rectangle in the overlay)
- **Output**: relative pixel delta applied to the system cursor via PyAutoGUI

What you should feel:

- Slow, small index-tip movement → slow, precise cursor (gain ~1.0, 0–1 palm-width/s)
- Fast, large index-tip movement → fast, large cursor jumps (gain ramps up to ~3.0 above 3 palm-width/s)
- Hand moves closer to the camera → cursor becomes less sensitive (depth compensation via palm-width normalization)
- Sub-`v_jitter` (0.20 palm-width/s) movement is suppressed — this is your rest tolerance for hand tremor

### 2. Left click (release-to-commit pinch)

- **Trigger**: thumb tip + index tip come within normalized distance 0.05 of each other (palm-width normalized), confirmed for 2 frames → `PINCH_PRESSED`
- **Hold**: stay pinched → state goes to `PINCH_HOLD` (no click yet, no repeat)
- **Release**: distance exceeds 0.075, confirmed for 2 frames → **emit one left click**, enter COOLDOWN 150ms

What you should feel:

- Pinch and hold → no click happens, but the bottom bar will fill green (press zone)
- Release → one click
- Try to click again immediately → COOLDOWN 150ms blocks the next click
- Pinching through the click is wrong — let go to fire

This is the single biggest change from v1. Press-to-click is gone; release-to-commit is what every VR / AR product uses for a reason.

### 3. Grab scroll (active in ACTIVE)

- **Grab pose**: thumb-index distance < 1.8 × palm-width AND at least 2 of {index, middle, ring, pinky} are curled (tip-to-palm-center distance < 1.65 × mcp-to-palm-center distance)
- **Hold** the grab pose for 120ms → state goes to `GRABBING`
- **Move** your hand up or down (any frame where hand-center y-delta > 0.015 normalized) → state goes to `DRAGGING`, scroll delta = `−y_delta × 180` (clamped to ±18 per frame)
- **Release** the grab pose or move out of frame → state `RELEASED`, scroll stops, 120ms grace before reset

What you should feel:

- Static grab pose held still → no scroll, `Grab: state=GRABBING active=no`
- Grab and pull your hand down → page scrolls up (natural touchpad-like direction)
- Grab and push up → page scrolls down
- Let go → scroll stops cleanly

### 4. Swipe shortcut (active in ACTIVE, AND not currently in a grab pose)

- **Trigger**: index tip moves >= 0.18 normalized distance in one direction within 900ms
- **Axis ratio**: must be 1.4× more pronounced on one axis than the other (so a diagonal does not fire)
- **Action**: `SWIPE_LEFT` / `SWIPE_RIGHT` press the left / right arrow key 4 times; `SWIPE_UP` / `SWIPE_DOWN` scroll ±20
- **Cooldown** 700ms between swipes

This is the existing v1 behavior preserved for users who rely on it.

## Debug overlay

The OpenCV window shows two things in addition to the camera feed:

### Top-left status panel (9 lines)

```
Mode: ACTIVE | DEBUG                              <- whether pointer injects into OS
Engagement: ACTIVE (active=yes, reason=hotkey)     <- FSM state + activation reason
Pointer: state=ACTIVE v=1.23 gain=1.45 depth=0.87  <- pointer engine telemetry
Pinch: state=PINCH_HOLD d=0.038 (close=0.050 ...)  <- current pinch distance + thresholds
Grab: state=DRAGGING active=yes scroll=-7          <- grab scroll state
FPS: 58.3                                           <- end-to-end frame rate
Frame age: 16 ms                                    <- time from camera to debug draw
Backend: CAP_DSHOW                                  <- which OpenCV backend is in use
Hand: Right (0.92)                                  <- handedness + confidence
```

### Bottom-left pinch threshold bar

A 280-pixel horizontal bar with two marker lines:

- **Green line** at 0.05 normalized distance = `pinch_close` threshold (press trigger)
- **Blue line** at 0.075 normalized distance = `pinch_open` threshold (release trigger)
- **Fill color**:
  - Green = currently in press zone (distance < 0.05)
  - Blue = currently in hold zone (0.05 ≤ distance < 0.075)
  - Gray = open (distance ≥ 0.075)

### Other overlay elements

- Green skeleton with dots: 21 hand landmarks
- Orange rectangle: control region
- Cyan circle + dot on index tip: raw index position
- Filled orange box top-left: status panel background

## Tuning

All thresholds are dataclass fields. Edit `src/handmouse/config.py` (for camera / pointer region) or pass to constructors in `src/handmouse/app.py`:

| Knob | Where | What it does | Default |
|---|---|---|---|
| `CameraConfig.width/height` | `config.py` | Capture resolution | 640×480 |
| `CameraConfig.backend_preference` | `config.py` | DSHOW→MSMF→ANY | (`CAP_DSHOW`, `CAP_MSMF`, `CAP_ANY`) |
| `CameraConfig.buffer_size` | `config.py` | OpenCV internal queue | 1 (latest-frame) |
| `ControlRegion` | `config.py` (used by PointerEngine) | Active region in camera frame | 12%–88% × 10%–90% |
| `PointerEngineConfig.v_jitter` | `app.py` | Movement below this is suppressed | 0.20 palm-width/s |
| `PointerEngineConfig.v_mid` | `app.py` | Speed at which gain = 1.0 | 1.0 |
| `PointerEngineConfig.v_fast` | `app.py` | Speed at which gain = g_hi | 3.0 |
| `PointerEngineConfig.g_lo` | `app.py` | Gain at very slow speed | 0.85 |
| `PointerEngineConfig.g_hi` | `app.py` | Max gain at high speed | 3.0 |
| `PointerEngineConfig.depth_gamma` | `app.py` | Depth compensation exponent | 0.9 |
| `PointerEngineConfig.z_min / z_max` | `app.py` | Depth compensation clamps | 0.70 / 1.25 |
| `EngagementConfig.palm_hold_ms` | `app.py` | How long to hold open palm to engage | 200 ms |
| `EngagementConfig.missing_frames_to_idle` | `app.py` | How many missing-hand frames to disengage | 4 |
| `GestureConfig.pinch_close` | `app.py` | Press trigger threshold | 0.05 |
| `GestureConfig.pinch_open` | `app.py` | Release trigger threshold | 0.075 |
| `GestureConfig.confirm_frames` | `app.py` | Frames to confirm pinch press | 2 |
| `GestureConfig.release_confirm_frames` | `app.py` | Frames to confirm pinch release | 2 |
| `GestureConfig.cooldown_ms` | `app.py` | Time after click before another is allowed | 150 ms |
| `GrabScrollConfig.hold_ms` | `app.py` | How long to hold grab before scrolling | 120 ms |
| `GrabScrollConfig.scroll_sensitivity` | `app.py` | Multiplier on hand-center y-delta | 180 |
| `GrabScrollConfig.max_scroll_per_frame` | `app.py` | Clamp on per-frame scroll | 18 |

## Safety

- App starts in **IDLE**. Real mouse control is OFF until you press `m` (or hold an open palm for 200ms).
- `m` toggles ACTIVE / IDLE.
- `q` exits immediately.
- PyAutoGUI failsafe is enabled — moving the system cursor to a screen corner aborts the loop.
- After 4 consecutive frames with no hand detected → automatic COOLDOWN 100ms → IDLE.
- The system **never** defaults to a state where it outputs mouse events on a heuristic alone.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `RuntimeError: Could not read a frame from the camera` | Windows Settings → Privacy → Camera, allow desktop apps. Close other apps using the camera. Change `DEFAULT_CONFIG.camera.index` (0, 1, 2, …) until one works. |
| `HandLandmarker` fails on first run | Network or storage permission issue. Manually download from `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` and set `$env:HANDMOUSE_MODEL_PATH`. |
| Pointer drifts even when hand is still | Increase `PointerEngineConfig.v_jitter` (default 0.20). If drifting only when hand moves in z, increase `z_min` (less depth correction = less z sensitivity). |
| Pinch fires too easily / not at all | Adjust `GestureConfig.pinch_close` (lower = easier press) and `pinch_open` (lower = easier release). |
| Grab scroll fires while just opening my hand | Make the grab pose more obviously closed — at least 2 fingers visibly curled past ratio 1.65. Or increase `min_curled_fingers` from 2 to 3. |
| App starts clicking / moving cursor without me | Press `m` to go IDLE, then `q` to quit. Check engagement reason in overlay: if it shows `palm_hold`, your resting hand is being mistaken for a palm. Try keyboard-only activation by holding the hand as a fist. |
| FPS is below 30 | Check `Backend` line. If it says `CAP_ANY`, edit `config.py` to put `CAP_DSHOW` first. If FPS is still low at 640×480, your CPU is too slow for MediaPipe — there is no further v2 optimization to apply without switching hardware. |
| Cursor jumps in big jumps when re-engaging | This is the pointer engine re-anchoring on the new index-tip position. Expected. Keep your hand in roughly the same position before and after pressing `m`. |

## Architecture

```
src/handmouse/
├── camera.py             Camera with DSHOW→MSMF→ANY preference, buffer=1, fps=60
├── hand_tracker.py       MediaPipe HandLandmarker in VIDEO mode, detect_for_video(ms)
├── pointer_engine.py     Relative pointer: adaptive gain + depth comp + dead zone
├── engagement.py         IDLE/ARMED/ACTIVE/COOLDOWN state machine
├── gesture_detector.py   Pinch with release-to-commit, double threshold
├── grab_scroll_detector.py  Grab+move=scroll, release=stop
├── shortcut_detector.py  Index-finger swipe → arrow / scroll
├── mouse_controller.py   PyAutoGUI wrapper with FAILSAFE
├── shortcut_controller.py  Translates swipe actions to keys / scroll
├── debug_view.py         OpenCV overlay: status panel + pinch bar
├── config.py             DEFAULT_CONFIG dataclass
└── app.py                Main loop wiring everything together
```

Read order if you want to understand the code: `config.py` → `engagement.py` → `pointer_engine.py` → `gesture_detector.py` → `grab_scroll_detector.py` → `app.py`.

## Research

`docs/research/`:
- `phase2-library-evaluation.md` — why MediaPipe Hand Landmarker (Tasks, full/float16) over alternatives
- `phase3-performance-optimization.md` — why VIDEO mode + 640×480 + buffer=1
- `phase4-pointer-control-paradigms.md` — why relative + adaptive gain + double threshold + explicit activation
- `handmouse-v2-design.md` — the executable spec, 522 lines
