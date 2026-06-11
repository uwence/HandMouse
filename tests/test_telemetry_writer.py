import tempfile
from pathlib import Path

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
