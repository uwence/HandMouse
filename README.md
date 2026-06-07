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

## Grab Scroll

This branch experiments with a grab-scroll gesture instead of continuous mouse movement.

In debug mode, detected grab state and scroll deltas are only displayed in the overlay. After pressing `m`, detected grab-scroll deltas execute real scroll events.

- Make a claw/grab hand shape, like grabbing the page.
- Hold the grab shape briefly until `Active: yes` appears.
- Move the grabbed hand up or down to scroll the page.
- Release the hand shape or move out of view to stop and reset.

The detector intentionally requires a grab pose before scrolling. Normal hand movement should not execute shortcuts.

## Safety

The app starts in debug mode, so hand tracking, grab state, and scroll deltas can be inspected before real scroll events are enabled.

## Troubleshooting

- If startup says it cannot read a frame from the camera, check Windows camera permissions, close other apps using the camera, and try a different camera index in `DEFAULT_CONFIG`.
- If the hand model download fails, manually download `hand_landmarker.task` from the MediaPipe model URL shown in the error, then set `HANDMOUSE_MODEL_PATH`.
- If shortcut execution feels noisy, press `m` to return to debug mode or press `q` to quit.
