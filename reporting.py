"""Generate simulation reports from events.

Usage:
    python3 reporting.py runs/run_YYYYMMDD_seed42_1
"""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from schemas import AGENT_IDS

FIRM_FIELDS = [
    "week", "customers", "cumulative_customer_weeks", "new_features",
    "completed_features", "features_completed_count", "outdated_work",
    "messages", "words", "send_hours", "receive_hours", "communication_hours",
        "broadcast_messages", "private_messages", "work_hours", "unused_hours",
    "excess_work_hours", "outdated_hours", "communication_rounds_used",
        "communication_stop_reason",
]
AGENT_FIELDS = [
    "week", "agent", "messages", "words", "send_hours", "receive_hours",
        "communication_hours", "work_hours",
    "unused_hours", "invalid_actions", "tokens_used",
]


def read_jsonl(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(row[key]) if isinstance(row.get(key),
                (dict, list)) else row.get(key, "") for key in fields})


def measure(events, weekly_history):
    by_week = defaultdict(list)
    by_week_agent = defaultdict(list)
    for event in events:
        by_week[event["week"]].append(event)
        if event.get("agent") in AGENT_IDS:
            by_week_agent[event["week"], event["agent"]].append(event)

    firm_rows, agent_rows = [], []

    for entry in weekly_history:
        week = entry["week"]
        evs = by_week[week]
        chats = [e for e in evs if e["type"] == "chat"]
        actions = [e for e in evs if e["type"] == "action_log"]
        excess = sum(e.get("excess_hours",
            0) for e in evs if e["type"] == "feature_completed")
        row = {
            **entry,
            "features_completed_count": len(entry["completed_features"]),
            "messages": len(chats),
            "words": sum(e["words"] for e in chats),
            "send_hours": round(sum(e["cost_hours"] for e in chats), 6),
            "receive_hours": round(sum(e.get("total_receive_cost_hours",
                0) for e in chats), 6),
            "communication_hours": round(sum(e.get("total_cost_hours",
                e["cost_hours"]) for e in chats), 6),
            "broadcast_messages": sum(e["recipient"] == "all" for e in chats),
            "private_messages": sum(e["recipient"] != "all" for e in chats),
            "work_hours": round(sum(e["hours_worked"] for e in actions), 6),
            "unused_hours": round(sum(e["unused_hours"] for e in actions), 6),
            "excess_work_hours": round(excess, 6),
            "outdated_hours": round(sum(v["hours_lost"] for v in entry["outdated_work"].values()), 6),
        }
        firm_rows.append(row)
        for agent in AGENT_IDS:
            aevs = by_week_agent[week, agent]
            sent = [e for e in aevs if e["type"] == "chat"]
            received = [e for e in chats if agent in e.get("recipients", [])]
            send_hours = sum(e["cost_hours"] for e in sent)
            receive_hours = sum(e["receive_cost_per_agent_hours"] for e in received)
            spent = next((e for e in aevs if e["type"] == "action_log"), None)
            invalid = sum(e["type"] in {"invalid_discussion_action",
                "invalid_allocation_action", "allocation_rejected",
                    "action_rejected"} for e in aevs)
            base = {
                "week": week, "agent": agent, "messages": len(sent),
                "words": sum(e["words"] for e in sent),
                "send_hours": round(send_hours, 6),
                "receive_hours": round(receive_hours, 6),
                "communication_hours": round(send_hours + receive_hours, 6),
                "work_hours": spent["hours_worked"] if spent else "",
                "unused_hours": spent["unused_hours"] if spent else "",
                "invalid_actions": invalid,
                "tokens_used": sum(e.get("tokens",
                    0) for e in aevs if e["type"] == "llm_usage"),
            }
            agent_rows.append(base)

    all_chats = [e for e in events if e["type"] == "chat"]
    all_actions = [e for e in events if e["type"] == "action_log"]
    totals = {
        "total_messages": len(all_chats),
        "total_words": sum(e["words"] for e in all_chats),
        "messages_by_agent": {a: sum(e["agent"] == a for e in all_chats) for a in AGENT_IDS},
        "total_send_hours": round(sum(e["cost_hours"] for e in all_chats), 6),
        "total_receive_hours": round(sum(e.get("total_receive_cost_hours",
            0) for e in all_chats), 6),
        "total_communication_hours": round(sum(e.get("total_cost_hours",
            e["cost_hours"]) for e in all_chats), 6),
        "total_broadcast_messages": sum(e["recipient"] == "all" for e in all_chats),
        "total_private_messages": sum(e["recipient"] != "all" for e in all_chats),
        "total_work_hours": round(sum(e["hours_worked"] for e in all_actions), 6),
        "total_unused_hours": round(sum(e["unused_hours"] for e in all_actions), 6),
        "total_excess_work_hours": round(sum(r["excess_work_hours"] for r in firm_rows), 6),
        "total_outdated_hours": round(sum(r["outdated_hours"] for r in firm_rows), 6),
        "invalid_action_attempts": sum(e["type"] in {"invalid_discussion_action",
            "invalid_allocation_action", "allocation_rejected",
                "action_rejected"} for e in events),
        "api_errors": sum(e["type"] == "api_error" for e in events),
    }
    return firm_rows, agent_rows, totals


def save_reports(output, events, history, summary):
    output = Path(output)
    firm, agents, totals = measure(events, history)

    write_csv(output / "firm_week.csv", FIRM_FIELDS, firm)
    write_csv(output / "agent_week.csv", AGENT_FIELDS, agents)

    enriched = dict(summary)
    enriched.update(totals)
    enriched["completed_successfully"] = len(history) == enriched.get("planned_weeks",
        len(history)) and not any(
        e["type"] in {"api_error", "discussion_failed",
            "allocation_failed"} for e in events
    )
    enriched.pop("planned_weeks", None)

    (output / "summary.json").write_text(json.dumps(enriched, indent=2),
        encoding="utf-8")
    return enriched



def main():
    parser = argparse.ArgumentParser(description="Generate simulation reports from events")
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    folder = args.run_dir
    events = read_jsonl(folder / "events.jsonl")
    history = [e for e in events if e["type"] == "week_ended"]
    summary = json.loads((folder / "summary.json").read_text())
    config = json.loads((folder / "config.json").read_text())
    summary["planned_weeks"] = config["weeks"]
    save_reports(folder, events, history, summary)
    print(f"Updated firm_week.csv, agent_week.csv, and summary.json in {folder}")


if __name__ == "__main__":
    main()