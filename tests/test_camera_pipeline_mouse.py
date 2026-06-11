from __future__ import annotations

import time
import sys
from unittest.mock import MagicMock
import pytest

from handmouse.config import CameraConfig
from handmouse.camera import Camera
from handmouse.thread_pipeline import CameraReader, InferenceWorker, FrameBuffer, ResultBuffer
from handmouse.mouse_controller import MouseController, MouseFailsafeTriggered
from handmouse.types import ScreenPoint, ScreenDelta


def test_camera_open_and_read(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_capture = MagicMock()
    mock_capture.isOpened.return_value = True
    mock_capture.read.return_value = (True, "camera_frame")

    mock_cv2 = MagicMock()
    mock_cv2.VideoCapture.return_value = mock_capture
    mock_cv2.CAP_PROP_FRAME_WIDTH = 3
    mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
    mock_cv2.CAP_PROP_FPS = 5
    mock_cv2.CAP_PROP_BUFFERSIZE = 38
    mock_cv2.flip.side_effect = lambda frame, code: frame

    monkeypatch.setitem(sys.modules, "cv2", mock_cv2)

    config = CameraConfig(width=640, height=480, index=0, backend_preference=("CAP_DSHOW",))
    camera = Camera(config)
    
    camera.open()
    assert camera.backend_name == "CAP_DSHOW"

    ok, frame = camera.read()
    assert ok is True
    assert frame == "camera_frame"

    camera.release()
    assert mock_capture.release.call_count > 0


def test_thread_pipeline_frame_buffer() -> None:
    fb = FrameBuffer()
    fb.set("frame1", 100)
    
    f, t = fb.get()
    assert f == "frame1"
    assert t == 100

    fb.clear()
    fb.set("frame2", 200)
    f, t = fb.get()
    assert f == "frame2"
    assert t == 200


def test_thread_pipeline_result_buffer() -> None:
    rb = ResultBuffer()
    mock_res = MagicMock()
    rb.set(mock_res, "frame1", 100)
    
    res, f, t = rb.get()
    assert res == mock_res
    assert f == "frame1"
    assert t == 100


def test_camera_reader_and_inference_worker_threads() -> None:
    # Set up mock camera
    mock_camera = MagicMock()
    mock_camera.config = CameraConfig(width=640, height=480, index=0, fps_target=100)
    mock_camera.read.return_value = (True, "mock_frame")

    # Set up mock tracker
    mock_tracker = MagicMock()
    mock_tracker.process.return_value = "mock_landmarks"

    reader = CameraReader(mock_camera)
    worker = InferenceWorker(reader, mock_tracker)

    # Start threads
    reader.start()
    worker.start()

    # Wait for frame to be processed
    time.sleep(0.05)

    # Verify frame was set
    has_res = worker.buffer.wait_new_result(timeout=0.1)
    assert has_res is True
    res, frame, ts = worker.buffer.get()
    assert res == "mock_landmarks"
    assert frame == "mock_frame"

    # Stop threads
    reader.stop()
    worker.stop()
    reader.join(timeout=0.5)
    worker.join(timeout=0.5)


def test_mouse_controller_pyautogui_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MouseController, "_dispatch_move", lambda self, p: self._move_pyautogui(p))
    monkeypatch.setattr(MouseController, "_dispatch_move_relative", lambda self, d: self._move_relative_pyautogui(d))
    mock_pyautogui = MagicMock()
    
    class FakeFailSafeException(Exception):
        pass

    mock_pyautogui.FailSafeException = FakeFailSafeException
    monkeypatch.setattr("handmouse.mouse_controller.pyautogui", mock_pyautogui)

    mouse = MouseController()
    mouse.set_control_enabled(True)
    assert mouse.is_control_enabled() is True

    # Test move
    mouse.move(ScreenPoint(100, 200))
    mock_pyautogui.moveTo.assert_called_once_with(100, 200, duration=0)

    # Test move_relative
    mouse.move_relative(ScreenDelta(10, -10))
    mock_pyautogui.moveRel.assert_called_once_with(10, -10, duration=0)

    # Test left_click
    mouse.left_click()
    mock_pyautogui.click.assert_called_with(button="left")

    # Test right_click
    mouse.right_click()
    mock_pyautogui.click.assert_called_with(button="right")

    # Test double_click
    mouse.double_click()
    mock_pyautogui.doubleClick.assert_called_once_with(button="left")

    # Test left_down
    mouse.left_down()
    mock_pyautogui.mouseDown.assert_called_once_with(button="left")

    # Test left_up
    mouse.left_up()
    mock_pyautogui.mouseUp.assert_called_once_with(button="left")


def test_mouse_controller_failsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MouseController, "_dispatch_move", lambda self, p: self._move_pyautogui(p))
    mock_pyautogui = MagicMock()
    
    class FakeFailSafeException(Exception):
        pass

    mock_pyautogui.FailSafeException = FakeFailSafeException
    mock_pyautogui.moveTo.side_effect = FakeFailSafeException("corner")
    monkeypatch.setattr("handmouse.mouse_controller.pyautogui", mock_pyautogui)

    mouse = MouseController()
    mouse.set_control_enabled(True)

    with pytest.raises(MouseFailsafeTriggered):
        mouse.move(ScreenPoint(0, 0))


def test_inference_worker_live_stream_mode() -> None:
    # Set up mock camera
    mock_camera = MagicMock()
    mock_camera.config = CameraConfig(width=640, height=480, index=0, fps_target=100)
    mock_camera.read.return_value = (True, "mock_frame")

    # Set up mock tracker
    mock_tracker = MagicMock()
    
    # Mock that it's running in LIVE_STREAM mode
    class FakeRunningMode:
        LIVE_STREAM = 1
        VIDEO = 2
    mock_tracker._running_mode = 1
    
    # Store the registered callback
    registered_callback = None
    def register_callback(callback):
        nonlocal registered_callback
        registered_callback = callback
    mock_tracker.register_callback = register_callback

    # Monkeypatch to avoid real mediapipe RunningMode import crash
    import sys
    from types import ModuleType
    mp_tasks = ModuleType("mediapipe.tasks.python.vision")
    mp_tasks.RunningMode = FakeRunningMode
    sys.modules["mediapipe.tasks.python.vision"] = mp_tasks
    sys.modules["mediapipe.tasks.python"] = ModuleType("mediapipe.tasks.python")
    sys.modules["mediapipe.tasks"] = ModuleType("mediapipe.tasks")
    sys.modules["mediapipe"] = ModuleType("mediapipe")

    reader = CameraReader(mock_camera)
    worker = InferenceWorker(reader, mock_tracker)

    # Verify callback was registered on tracker
    assert registered_callback is not None

    # Put a frame in the reader's buffer
    reader.buffer.set("test_frame", 1234)

    # Mock process_async
    process_async_calls = []
    def process_async(frame, timestamp):
        process_async_calls.append((frame, timestamp))
    mock_tracker.process_async = process_async

    # Trigger worker.run logic for one frame
    if reader.buffer.wait_new_frame(timeout=0.1):
        reader.buffer.clear()
        frame, timestamp_ms = reader.buffer.get()
        assert frame == "test_frame"
        assert timestamp_ms == 1234
        
        # Simulating run() block
        if worker._is_live_stream:
            with worker._frame_lock:
                worker._frame_cache[timestamp_ms] = frame
            worker.tracker.process_async(frame, timestamp_ms)

    assert len(process_async_calls) == 1
    assert process_async_calls[0] == ("test_frame", 1234)
    assert worker._frame_cache[1234] == "test_frame"

    # Now simulate callback firing from tracker
    registered_callback("mock_result", None, 1234)

    # Verify the result buffer is populated correctly
    res, frame, ts = worker.buffer.get()
    assert res == "mock_result"
    assert frame == "test_frame"
    assert ts == 1234
    
    # Verify the frame cache is cleaned up
    assert 1234 not in worker._frame_cache
