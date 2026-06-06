# HandMouse

Windows-native Python prototype for controlling the mouse with webcam-based hand gestures.

## Windows Setup

1. Install Python 3.11 or newer for Windows.
2. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install the project and development dependencies:

```powershell
python -m pip install -e ".[dev]"
```

## Run

```powershell
python -m handmouse.app
```

On first run, HandMouse downloads the MediaPipe hand landmarker model to
`%USERPROFILE%\.handmouse\models\hand_landmarker.task`. To use a pre-downloaded
model file instead, set:

```powershell
$env:HANDMOUSE_MODEL_PATH = "C:\path\to\hand_landmarker.task"
```

## Controls

- `m`: toggle between debug mode and real mouse-control mode.
- `q`: quit the application.

## Mouse Behavior

HandMouse uses relative movement by default. When real mouse-control mode is enabled, moving your index finger moves the cursor by a matching relative delta, similar to a physical mouse or touchpad. The first detected frame anchors the hand position and does not move the cursor, so re-entering the frame should not cause a large jump.

Thumb-index pinch still triggers left click. During pinch/click/cooldown, movement is paused and the relative anchor is reset so releasing the gesture does not drag the cursor back.

## Safety

The app starts in debug mode, so hand tracking and cursor targets can be inspected before real mouse movement is enabled. PyAutoGUI failsafe stays enabled, allowing the real mouse to be moved to a screen corner to abort if control becomes unstable.

## Troubleshooting

- If startup says it cannot read a frame from the camera, check Windows camera permissions, close other apps using the camera, and try a different camera index in `DEFAULT_CONFIG`.
- If the hand model download fails, manually download `hand_landmarker.task` from the MediaPipe model URL shown in the error, then set `HANDMOUSE_MODEL_PATH`.
- If real mouse movement feels unsafe, press `m` to return to debug mode, press `q` to quit, or move the physical mouse to a screen corner to trigger the PyAutoGUI failsafe.
