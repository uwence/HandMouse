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
