import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1])
rows = []

columns = [
    "experiment", "value", "status",
    "weeks_completed", "final_customers", "cumulative_customers",
    "explored_branches",
    "total_msg_sent", "total_msg_received", "direct_msg", "zero_msg_weeks",
    "total_chat_words", "total_chat_hours", "total_work_hours",
    "total_underallocated_hours", "total_overallocated_hours",
    "allocation_rejections", "total_tokens", "seed"
]

for folder in sorted(root.iterdir()):
    if not folder.is_dir() or "_failed_" in folder.name:
        continue

    match = re.fullmatch(r"(.+)_seed(\d+)(?:_.*)?", folder.name)
    if not match:
        continue

    condition, seed = match.groups()
    numeric_match = re.fullmatch(r"(.+)_(-?\d+(?:\.\d+)?)", condition)

    if numeric_match:
        experiment, value = numeric_match.groups()
        value = float(value)
    else:
        experiment, value = condition, ""

    events_path = folder / "events.jsonl"
    if not events_path.exists():
        continue

    with events_path.open(encoding="utf-8") as f:
        events = [json.loads(line) for line in f if line.strip()]

    def get_events(event_type):
        return [e for e in events if e.get("type") == event_type]

    weeks = get_events("week_ended")
    chats = get_events("chat")
    actions = get_events("action_log")
    features = get_events("feature_completed")
    messages_by_week = Counter(e["week"] for e in chats)

    explored_branches = {
        feature.split("_")[1]
        for e in actions
        for feature, hours in e.get("allocations", {}).items()
        if hours > 0 and re.fullmatch(r"feature_\d+(?:_\d+)*", feature)
    }

    row = {
        "experiment": experiment,
        "value": value,
        "status": "completed" if len(weeks) == 8 else "incomplete",
        "weeks_completed": len(weeks),
        "final_customers": weeks[-1]["customers"] if weeks else 0,
        "cumulative_customers": weeks[-1]["cumulative_customer_weeks"] if weeks else 0,
        "explored_branches": len(explored_branches),
        "total_msg_sent": len(chats),
        "total_msg_received": sum(len(e.get("recipients", [])) for e in chats),
        "direct_msg": sum(e.get("recipient") not in ("all", None) for e in chats),
        "zero_msg_weeks": sum(messages_by_week[w["week"]] == 0 for w in weeks),
        "total_chat_words": sum(e.get("words", 0) for e in chats),
        "total_chat_hours": round(sum(e.get("total_cost_hours", 0) for e in chats), 6),
        "total_work_hours": round(sum(e.get("hours_worked", 0) for e in actions), 6),
        "total_underallocated_hours": round(sum(e.get("unused_hours",
            0) for e in actions), 6),
        "total_overallocated_hours": round(sum(e.get("excess_hours",
            0) for e in features), 6),
        "allocation_rejections": len(get_events("allocation_rejected")),
        "total_tokens": sum(e.get("tokens", 0) for e in get_events("llm_usage")),
        "seed": int(seed),
    }
    rows.append(row)

rows.sort(key=lambda r: (r["experiment"],
    float(r["value"]) if r["value"] != "" else float("inf"), r["seed"]))

output = root / "comparison.csv"

with output.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=columns)
    writer.writeheader()
    writer.writerows(rows)

print(f"Saved {len(rows)} simulations to {output}")