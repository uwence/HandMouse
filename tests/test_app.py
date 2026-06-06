from handmouse.app import _apply_mouse_control, _mirror_frame
from handmouse.mouse_controller import MouseFailsafeTriggered


class FakeCv2:
    def __init__(self) -> None:
        self.calls: list[tuple[object, int]] = []

    def flip(self, frame: object, flip_code: int) -> object:
        self.calls.append((frame, flip_code))
        return ("mirrored", frame, flip_code)


def test_mirror_frame_flips_horizontally() -> None:
    cv2 = FakeCv2()
    frame = object()

    result = _mirror_frame(cv2, frame)

    assert result == ("mirrored", frame, 1)
    assert cv2.calls == [(frame, 1)]


class FailsafeMouse:
    def __init__(self) -> None:
        self.enabled = True

    def move(self, pointer_result: object) -> None:
        raise MouseFailsafeTriggered("corner")

    def left_click(self) -> None:
        raise AssertionError("click should not run after move failsafe")

    def set_control_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


def test_apply_mouse_control_disables_control_on_failsafe() -> None:
    mouse = FailsafeMouse()

    _apply_mouse_control(mouse, object(), should_click=True)

    assert mouse.enabled is False
