from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


class ReplayRunner:
    def __init__(self, telemetry_path: str | Path) -> None:
        self.telemetry_path = Path(telemetry_path)

    def run(self) -> dict[str, Any]:
        return self.summarize_records(self._iter_file_records())

    def _iter_file_records(self) -> Iterable[dict[str, Any]]:
        with self.telemetry_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue

    @staticmethod
    def summarize_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        events_count: Counter[str] = Counter()
        committed: Counter[str] = Counter()
        blocked: dict[str, Counter[str]] = defaultdict(Counter)
        dispatched: Counter[str] = Counter()
        frame_samples_total = 0
        frame_samples_hand_found = 0
        handedness: Counter[str] = Counter()

        for record in records:
            event = record.get("event")
            if event:
                events_count[event] += 1

            if event == "frame_sample":
                frame_samples_total += 1
                if record.get("hand_found"):
                    frame_samples_hand_found += 1
                label = record.get("handedness_label")
                if label:
                    handedness[str(label)] += 1

            if event == "gesture_decision":
                action = record.get("action", "unknown")
                if record.get("committed"):
                    committed[action] += 1
                else:
                    blocked[action][record.get("blocked_by", "unknown")] += 1

            if event == "action_dispatch" and record.get("executed"):
                dispatched[record.get("action", "unknown")] += 1

        return {
            "events": dict(events_count),
            "frame_samples": {
                "total": frame_samples_total,
                "hand_found": frame_samples_hand_found,
                "hand_found_pct": round((frame_samples_hand_found / frame_samples_total) * 100, 2)
                if frame_samples_total
                else 0.0,
                "handedness": dict(handedness),
            },
            "committed": dict(committed),
            "blocked": {action: dict(reasons) for action, reasons in blocked.items()},
            "dispatched": dict(dispatched),
        }


def analyze_telemetry(ndjson_path: str) -> None:
    report = ReplayRunner(ndjson_path).run()

    print(f"--- Telemetry Analysis: {ndjson_path} ---")
    print("Event Counts:")
    for event, count in report["events"].items():
        print(f"  {event}: {count}")

    print("\nFrame Sample Summary:")
    frame_samples = report["frame_samples"]
    print(f"  total: {frame_samples['total']}")
    print(f"  hand_found: {frame_samples['hand_found']} ({frame_samples['hand_found_pct']}%)")
    if frame_samples["handedness"]:
        print(f"  handedness: {frame_samples['handedness']}")
    else:
        print("  handedness: None")

    print("\nCommitted Decisions:")
    if not report["committed"]:
        print("  None")
    for action, count in report["committed"].items():
        print(f"  {action}: {count}")

    print("\nBlocked Decisions:")
    if not report["blocked"]:
        print("  None")
    for action, reasons in report["blocked"].items():
        print(f"  {action}: {reasons}")

    print("\nActions Dispatched (Executed):")
    if not report["dispatched"]:
        print("  None")
    for action, count in report["dispatched"].items():
        print(f"  {action}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="HandMouse Telemetry Replay Runner")
    parser.add_argument("ndjson_path", type=str, help="Path to the session .ndjson file")
    args = parser.parse_args()

    analyze_telemetry(args.ndjson_path)


if __name__ == "__main__":
    main()
