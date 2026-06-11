import json
import argparse
import sys
from typing import Dict, Any

def analyze_telemetry(ndjson_path: str) -> None:
    events_count = {"frame_sample": 0, "gesture_decision": 0, "action_dispatch": 0}
    actions_dispatched = {}
    
    with open(ndjson_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
                
            event = record.get("event")
            if event in events_count:
                events_count[event] += 1
                
            if event == "action_dispatch":
                action = record.get("action", "unknown")
                executed = record.get("executed", False)
                if executed:
                    actions_dispatched[action] = actions_dispatched.get(action, 0) + 1
                    
    print(f"--- Telemetry Analysis: {ndjson_path} ---")
    print("Event Counts:")
    for event, count in events_count.items():
        print(f"  {event}: {count}")
        
    print("\nActions Dispatched (Executed):")
    if not actions_dispatched:
        print("  None")
    for action, count in actions_dispatched.items():
        print(f"  {action}: {count}")

def main() -> None:
    parser = argparse.ArgumentParser(description="HandMouse Telemetry Replay Runner")
    parser.add_argument("ndjson_path", type=str, help="Path to the session .ndjson file")
    args = parser.parse_args()
    
    analyze_telemetry(args.ndjson_path)

if __name__ == "__main__":
    main()
