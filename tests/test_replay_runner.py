from __future__ import annotations

import os
from pathlib import Path
import uuid

from handmouse.replay.runner import ReplayRunner


def test_replay_runner_counts_blocked_and_committed_decisions() -> None:
    path = Path(os.getcwd()) / f".tmp-replay-{uuid.uuid4().hex}.ndjson"
    try:
        path.write_text(
            '{"event":"gesture_decision","action":"task_view","committed":false,"blocked_by":"quality_gate"}\n'
            '{"event":"gesture_decision","action":"click_left","committed":true}\n',
            encoding="utf-8",
        )

        report = ReplayRunner(path).run()

        assert report["committed"]["click_left"] == 1
        assert report["blocked"]["task_view"]["quality_gate"] == 1
    finally:
        path.unlink(missing_ok=True)


def test_replay_runner_summarizes_hand_presence_and_handedness() -> None:
    path = Path(os.getcwd()) / f".tmp-replay-{uuid.uuid4().hex}.ndjson"
    try:
        path.write_text(
            '{"event":"frame_sample","hand_found":true,"handedness_label":"Left"}\n'
            '{"event":"frame_sample","hand_found":false}\n'
            '{"event":"frame_sample","hand_found":true,"handedness_label":"Right"}\n',
            encoding="utf-8",
        )

        report = ReplayRunner(path).run()

        assert report["frame_samples"]["total"] == 3
        assert report["frame_samples"]["hand_found"] == 2
        assert report["frame_samples"]["hand_found_pct"] == 66.67
        assert report["frame_samples"]["handedness"]["Left"] == 1
        assert report["frame_samples"]["handedness"]["Right"] == 1
    finally:
        path.unlink(missing_ok=True)
