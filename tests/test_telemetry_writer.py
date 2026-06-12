import tempfile
from pathlib import Path
import json

from handmouse.telemetry.writer import TelemetryWriter


def test_telemetry_writer_accepts_explicit_log_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "custom.ndjson"
        writer = TelemetryWriter(log_file=str(log_file), enabled=True)
        try:
            assert Path(writer.log_file) == log_file
            assert Path(writer.log_dir) == Path(tmpdir)
        finally:
            writer.close()


def test_telemetry_writer_overwrites_explicit_log_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        log_file = Path(tmpdir) / "custom.ndjson"
        log_file.write_text('{"old": true}\n', encoding="utf-8")
        writer = TelemetryWriter(log_file=str(log_file), enabled=True)
        try:
            writer.log("frame_sample", {"ts_ms": 1})
        finally:
            writer.close()

        rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["event"] == "frame_sample"
        assert rows[0]["ts_ms"] == 1
