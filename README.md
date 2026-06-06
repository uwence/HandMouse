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

## Controls

- `m`: toggle between debug mode and real mouse-control mode.
- `q`: quit the application.

## Safety

The app starts in debug mode, so hand tracking and cursor targets can be inspected before real mouse movement is enabled. PyAutoGUI failsafe stays enabled, allowing the real mouse to be moved to a screen corner to abort if control becomes unstable.
