from handmouse.app import _mirror_frame


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
