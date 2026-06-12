import json
import os
import queue
import threading
import time
from typing import Any, Dict

class TelemetryWriter:
    """Asynchronous NDJSON writer for telemetry events."""
    def __init__(
        self,
        log_dir: str = "~/.handmouse/telemetry",
        enabled: bool = True,
        log_file: str | None = None,
    ):
        self.enabled = enabled
        if not enabled:
            return
            
        if log_file is not None:
            self.log_file = os.path.expanduser(log_file)
            self.log_dir = os.path.dirname(self.log_file) or "."
            self._file_mode = "w"
        else:
            self.log_dir = os.path.expanduser(log_dir)
            timestamp = time.strftime("%Y-%m-%dT%H-%M-%SZ")
            self.log_file = os.path.join(self.log_dir, f"session_{timestamp}.ndjson")
            self._file_mode = "a"
        os.makedirs(self.log_dir, exist_ok=True)
        
        self._queue = queue.Queue(maxsize=10000)
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="TelemetryWriter")
        self._thread.start()
        
    def log(self, event_name: str, payload: Dict[str, Any]) -> None:
        if not self.enabled:
            return
            
        record = {
            "event": event_name,
            "ts_wall_ms": int(time.time() * 1000),
        }
        record.update(payload)
        
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            # Drop events if the queue is full to avoid blocking the main thread
            pass
            
    def close(self) -> None:
        if not self.enabled:
            return
        self._stop_event.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
            
    def _worker(self) -> None:
        with open(self.log_file, self._file_mode, encoding="utf-8") as f:
            while not self._stop_event.is_set() or not self._queue.empty():
                try:
                    record = self._queue.get(timeout=0.1)
                    json.dump(record, f)
                    f.write("\n")
                    self._queue.task_done()
                except queue.Empty:
                    f.flush()
                except Exception as exc:
                    print(f"Telemetry Writer error: {exc}")

# Global singleton
_global_writer = None

def init_telemetry(enabled: bool = True, log_file: str | None = None) -> None:
    global _global_writer
    if _global_writer is not None:
        _global_writer.close()
    _global_writer = TelemetryWriter(enabled=enabled, log_file=log_file)

def log_event(event_name: str, payload: Dict[str, Any]) -> None:
    if _global_writer:
        _global_writer.log(event_name, payload)

def close_telemetry() -> None:
    global _global_writer
    if _global_writer:
        _global_writer.close()
        _global_writer = None
