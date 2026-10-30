"""Experiment constants, public feature specifications, and action validation."""
import os
from dataclasses import dataclass, field
from typing import Any

NUM_AGENTS = int(os.getenv("ASSISTAI_NUM_AGENTS", "10"))
WORKLOAD_SCALE = float(os.getenv("ASSISTAI_WORKLOAD_SCALE",
    "2" if NUM_AGENTS == 10 else "1"))
if NUM_AGENTS not in (5, 10) or WORKLOAD_SCALE <= 0:
    raise ValueError("Agent count must be 5 or 10, and workload scale must be positive")
AGENT_IDS = tuple(f"agent_{chr(97 + i)}" for i in range(NUM_AGENTS))

# Effort and prerequisites are known; true customer gains live ONLY in environment.py.
FEATURE_HOURS = {
    1: (110, 230, 165, 255),
    2: (195, 140, 275, 130),
    3: (75, 285, 120, 275),
    4: (245, 95, 240, 215)
}

FEATURES = {}
for branch, hours in FEATURE_HOURS.items():
    for level, required_hours in enumerate(hours):
        name = f"feature_{branch}" if level == 0 else f"feature_{branch}_{level}"
        previous = f"feature_{branch}" if level == 1 else f"feature_{branch}_{level - 1}"
        FEATURES[name] = {"hours": required_hours * WORKLOAD_SCALE,
            "prerequisites": [] if level == 0 else [previous]}



@dataclass


class Config:
    num_agents: int = NUM_AGENTS
    workload_scale: float = WORKLOAD_SCALE
    weeks: int = 8
    max_communication_rounds: int = 3
    hours_per_week: float = 40.0
    hours_per_message: float = 0.25
    receive_cost_multiplier: float = 0.5
    tokens_per_agent: int = 120000
    max_total_tokens: int = 750000
    seed: int = 42
    model: str = "gpt-4.1-mini"
    mock: bool = False
    history_window: int = -2  # -2=original behavior; -1=full; 0=current week; 1=current + previous
    attention_capacity: int = 5  # -1 = unlimited; otherwise last K visible messages
    private_memory: bool = False
    memory_max_words: int = 150
    decay_rate: float = -1

@dataclass


class AgentState:
    id: str
    remaining_hours: float = 40.0
    chat_turns: int = 0
    discussion_done: bool = False
    allocated: bool = False
    tokens_used: int = 0
    inbox: list[dict[str, Any]] = field(default_factory=list)
    private_memory: str = ""


def normalize_action(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"action_type": "INVALID", "error": "Invalid action"}
    result = dict(value)
    result["action_type"] = str(result.get("action_type", "INVALID")).upper()
    if result["action_type"] not in {"CHAT", "PASS", "ALLOCATE"}:
        return {"action_type": "INVALID", "error": "Invalid action"}
    return result