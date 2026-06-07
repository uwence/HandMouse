# HandMouse

Windows-native Python prototype for controlling shortcuts with webcam-based hand gestures.

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

- `m`: toggle between debug mode and real shortcut-execution mode.
- `q`: quit the application.

## Gesture Shortcuts

This branch experiments with discrete shortcut gestures instead of continuous mouse movement.

In debug mode, detected gestures are only displayed in the overlay. After pressing `m`, detected gestures execute these actions:

- Swipe left: press the left arrow key 4 times.
- Swipe right: press the right arrow key 4 times.
- Swipe up: scroll up by 20 units.
- Swipe down: scroll down by 20 units.

The detector uses broad, fast index-finger swipes and ignores diagonal or slow movement. This is intentionally less precise than mouse control, but should be more stable for presentations, page navigation, and reading.

## Safety

The app starts in debug mode, so hand tracking and detected shortcut actions can be inspected before real keyboard/scroll events are enabled.

## Troubleshooting

- If startup says it cannot read a frame from the camera, check Windows camera permissions, close other apps using the camera, and try a different camera index in `DEFAULT_CONFIG`.
- If the hand model download fails, manually download `hand_landmarker.task` from the MediaPipe model URL shown in the error, then set `HANDMOUSE_MODEL_PATH`.
- If shortcut execution feels noisy, press `m` to return to debug mode or press `q` to quit.
