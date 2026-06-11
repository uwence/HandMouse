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

The automated test suite currently passes in local verification. See `docs/research/handmouse-v2-design.md` for the design rationale.

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

When you run the app, you will now see a **System Tray Icon**. 
- **Left/Right Click** the tray icon to access:
  - **Settings (Basic & Advanced)**: Configure camera, pointer speed, and gestures.
  - **Profiles**: Switch between `Default`, `Aggressive`, and `Conservative` profiles on the fly.
  - **Toggle Active/Idle**: Manually engage/disengage mouse control.

All settings are automatically saved to `~/.handmouse/config.yaml`. Telemetry is also recorded in the background to `~/.handmouse/telemetry/` as NDJSON for later analysis. New recordings use telemetry `schema_version: 2`.

First run downloads the MediaPipe hand landmarker model (~7.5 MB) to `%USERPROFILE%\.handmouse\models\hand_landmarker.task`. To pre-place it:

```powershell
$env:HANDMOUSE_MODEL_PATH = "C:\path\to\hand_landmarker.task"
```

## Keyboard controls

| Key | Action |
|---|---|
| `m` | Toggle ACTIVE / IDLE (engage or disengage mouse control) |
| `Right Ctrl` | Hold-to-move clutch; pointer movement is allowed only while held and a valid move pose is active |
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

### 1. Pointer movement (active in ACTIVE, and only while holding `Right Ctrl`)

- **Control point**: index fingertip
- **Reference frame**: camera frame, with a default control region of 12%–88% horizontal × 10%–90% vertical (the orange rectangle in the overlay)
- **Output**: relative pixel delta applied to the system cursor via PyAutoGUI
- **Clutch**: hold `Right Ctrl`, then show the move pose (index + middle finger extended) until `Move mode` becomes `ACTIVE`

What you should feel:

- Without holding `Right Ctrl` → no real cursor movement, even if the hand is visible
- Slow, small index-tip movement → slow, precise cursor (gain ~1.0, 0–1 palm-width/s)
- Fast, large index-tip movement → fast, large cursor jumps (gain ramps up to ~3.0 above 3 palm-width/s)
- Hand moves closer to the camera → cursor becomes less sensitive (depth compensation via palm-width normalization)
- Sub-`v_jitter` (0.20 palm-width/s) movement is suppressed — this is your rest tolerance for hand tremor
- Releasing `Right Ctrl` → movement stops immediately

### 2. Left click / Drag (Pinch based on palm-span ratio)

- **Trigger**: thumb tip + index tip come within a normalized ratio of the palm span (default 0.5), confirmed for 2 frames → `PINCH_PRESSED`
- **Hold**: stay pinched → state goes to `PINCH_HOLD` (emits a drag hold intent, which will hold the left mouse button if moved)
- **Release**: distance exceeds 0.7 ratio to palm span, confirmed for 2 frames → **emit one click or release drag**, enter COOLDOWN 150ms

What you should feel:

- The pinch is now **depth-invariant** and size-invariant because it's calculated relative to your palm size, not absolute screen space.
- Pinch and hold without moving → no click happens until release.
- Pinch, hold, and move your hand → initiates a drag & drop action.
- Release → one click (or ends drag).
- Try to click again immediately → COOLDOWN 150ms blocks the next click.

### 3. Grab scroll (active in ACTIVE)

- **Grab pose**: thumb-index distance < 1.8 × palm-width AND at least 2 of {index, middle, ring, pinky} are curled.
- **Hold** the grab pose for 120ms → state goes to `GRABBING`.
- **Move** your hand up or down → state goes to `DRAGGING`. We added a **dead zone** to prevent accidental micro-scrolls.
- **Release** the grab pose or move out of frame → state `RELEASED`, scroll stops. There is a 120ms post-release grace period to prevent jittery exits.

### 4. Swipe shortcut (active in ACTIVE, AND not currently in a grab pose)

- **Anchor point**: Palm center (changed from index tip, making it much more robust against finger wiggles).
- **Trigger**: Palm center moves >= 0.18 normalized distance in one direction within 900ms.
- **Action**: `SWIPE_LEFT` / `SWIPE_RIGHT` switches virtual desktops or invokes `Win+D` (depending on configuration); `SWIPE_UP` / `SWIPE_DOWN` scrolls aggressively.
- **Risk Level**: Swipes are considered HIGH_RISK actions and are strictly gated by the TrackingQualityGate to prevent false positives when tracking is unstable.

## Debug overlay

The OpenCV window shows two things in addition to the camera feed:

### Top-left status panel (9 lines)

```
Mode: ACTIVE | DEBUG                                <- whether pointer injects into OS
Engagement: ACTIVE (active=yes, reason=hotkey)      <- FSM state + activation reason
Clutch: DOWN                                        <- `Right Ctrl` clutch state
Move mode: ACTIVE pose=yes                          <- move-mode gate state
Pointer: state=ACTIVE v=1.23 gain=1.45 depth=0.87  <- pointer engine telemetry
Pinch: state=PINCH_HOLD d=0.038 (close=0.050 ...)  <- current pinch distance + thresholds
Grab: state=DRAGGING active=yes scroll=-7          <- grab scroll state
FPS: 58.3                                          <- end-to-end frame rate
Frame age: 16 ms                                   <- time from camera to debug draw
Backend: CAP_DSHOW                                 <- which OpenCV backend is in use
Hand: Right (0.92)                                 <- handedness + confidence
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

All configurations are now automatically managed via a robust YAML engine and saved to `~/.handmouse/config.yaml`.
You can adjust the parameters visually via the System Tray **Settings** menu, or switch entire presets via the **Profiles** menu.

If you prefer to edit the configuration manually, you can open `~/.handmouse/config.yaml`. Any missing fields will be safely populated with defaults.

Hardening-related defaults now include:

- `schema_version: 2`
- `policy.high_risk_cooldown_ms: 500`
- `policy.explicit_confirm_required: true`
- `gesture_switches.win_d: false`

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
| `GestureConfig.pinch_close_ratio` | `app.py` | Press trigger ratio (distance / palm_span) | 0.5 |
| `GestureConfig.pinch_open_ratio` | `app.py` | Release trigger ratio (distance / palm_span) | 0.7 |
| `GestureConfig.confirm_frames` | `app.py` | Frames to confirm pinch press | 2 |
| `GestureConfig.release_confirm_frames` | `app.py` | Frames to confirm pinch release | 2 |
| `GestureConfig.cooldown_ms` | `app.py` | Time after click before another is allowed | 150 ms |
| `GrabScrollConfig.hold_ms` | `app.py` | How long to hold grab before scrolling | 120 ms |
| `GrabScrollConfig.scroll_sensitivity` | `app.py` | Multiplier on hand-center y-delta | 180 |
| `GrabScrollConfig.max_scroll_per_frame` | `app.py` | Clamp on per-frame scroll | 18 |

## Safety

- App starts in **IDLE**. Real mouse control is OFF until you press `m` (or hold an open palm for 200ms).
- `m` toggles ACTIVE / IDLE.
- Pointer movement also requires holding `Right Ctrl`; ACTIVE alone is not enough.
- `q` exits immediately.
- PyAutoGUI failsafe is enabled — moving the system cursor to a screen corner aborts the loop.
- After 4 consecutive frames with no hand detected → automatic COOLDOWN 100ms → IDLE.
- The system **never** defaults to a state where it outputs mouse events on a heuristic alone.

## 推荐使用姿势和测试流程

1. **启动**：运行 `python -m handmouse.app`
2. **激活**：按下 `m` 键，或保持张开手掌约 200ms。此时状态变为 `ACTIVE`。
3. **移动指针**：按住 `Right Ctrl` 键（或配置中指定的 `clutch` 键），并保持食指和中指伸直的“移动”手势。当 `Move mode` 变为 `ACTIVE` 后，移动手指即可控制鼠标。
4. **点击**：食指与拇指捏合（下方指示条变绿），然后松开（指示条变灰）即可触发左键点击。**必须松开**才会触发点击。
5. **滚动**：手握拳（抓取手势），保持不动 120ms 进入 `GRABBING` 状态。然后手上下移动，即可像触摸板一样滚动页面。松开恢复。
6. **调试信息**：留意左上角的 `Clutch: DOWN (hook: OK)`。如果 hook 状态为 FAILED，说明 `pynput` 监听失败。

## Troubleshooting

| Symptom | Fix |
|---|---|
| `RuntimeError: Could not read a frame from the camera` | Windows Settings → Privacy → Camera, allow desktop apps. Close other apps using the camera. Change `DEFAULT_CONFIG.camera.index` (0, 1, 2, …) until one works. |
| `HandLandmarker` fails on first run | Network or storage permission issue. Manually download from `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task` and set `$env:HANDMOUSE_MODEL_PATH`. |
| Pointer drifts even when hand is still | Increase `PointerEngineConfig.v_jitter` (default 0.20). If drifting only when hand moves in z, increase `z_min` (less depth correction = less z sensitivity). |
| Pinch fires too easily / not at all | Adjust `GestureConfig.pinch_close` (lower = easier press) and `pinch_open` (lower = easier release). |
| Grab scroll fires while just opening my hand | Make the grab pose more obviously closed — at least 2 fingers visibly curled past ratio 1.65. Or increase `min_curled_fingers` from 2 to 3. |
| App starts clicking / moving cursor without me | Press `m` to go IDLE, then `q` to quit. Check engagement reason in overlay: if it shows `palm_hold`, your resting hand is being mistaken for a palm. Movement should still require `Right Ctrl`; if it does not, the clutch listener failed and should be debugged. |
| FPS is below 30 | Check `Backend` line. If it says `CAP_ANY`, edit `config.py` to put `CAP_DSHOW` first. If FPS is still low at 640×480, your CPU is too slow for MediaPipe — there is no further v2 optimization to apply without switching hardware. |
| Cursor jumps in big jumps when re-engaging | This is the pointer engine re-anchoring on the new index-tip position. Expected. Keep your hand in roughly the same position before and after pressing `m`. |

## Architecture

```
src/handmouse/
├── camera.py             Camera with DSHOW→MSMF→ANY preference, buffer=1, fps=60
├── hand_tracker.py       MediaPipe HandLandmarker in VIDEO mode, detect_for_video(ms)
├── pointer_engine.py     Relative pointer: adaptive gain + depth comp + dead zone
├── clutch_input.py       Global clutch listener, defaulting to `Right Ctrl`
├── move_mode.py          NEUTRAL/ARMED/ACTIVE gate for hold-to-move
├── engagement.py         IDLE/ARMED/ACTIVE/COOLDOWN state machine
├── gesture_detector.py   Pinch with release-to-commit, double threshold
├── grab_scroll_detector.py  Grab+move=scroll, release=stop
├── shortcut_detector.py  Index-finger swipe → arrow / scroll
├── mouse_controller.py   PyAutoGUI wrapper with FAILSAFE
├── shortcut_controller.py  Translates swipe actions to keys / scroll
├── debug_view.py         OpenCV overlay: status panel + pinch bar
├── config/               YAML-backed config schema, defaults, and profiles
└── app.py                Main loop wiring everything together
```

Read order if you want to understand the code: `config/__init__.py` → `engagement.py` → `pointer_engine.py` → `gesture_detector.py` → `grab_scroll_detector.py` → `app.py`.

## Research

`docs/research/`:
- `phase2-library-evaluation.md` — why MediaPipe Hand Landmarker (Tasks, full/float16) over alternatives
- `phase3-performance-optimization.md` — why VIDEO mode + 640×480 + buffer=1
- `phase4-pointer-control-paradigms.md` — why relative + adaptive gain + double threshold + explicit activation
- `handmouse-v2-design.md` — the executable spec, 522 lines
