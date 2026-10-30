"""LLM agent and deterministic no-API smoke-test agent."""

import json
import os
from pathlib import Path

from response_parser import extract_action
from schemas import FEATURES, AGENT_IDS


PROMPT = (Path(__file__).parent / "prompts" / "peer_agent.md").read_text(
    encoding="utf-8"
)
PROMPT = (
    PROMPT.replace("{NUM_AGENTS}", str(len(AGENT_IDS)))
    .replace("{OTHER_AGENTS}", str(len(AGENT_IDS) - 1))
    .replace("{MAX_DIRECT_RECIPIENTS}", str(len(AGENT_IDS) - 2))
    .replace("{AGENTS}", ", ".join(AGENT_IDS))
)


def response_schema(phase, observation=None):
    if phase == "communication":
        properties = {
            "action_type": {"type": "string", "enum": ["CHAT", "PASS"]},
            "message": {
                "type": "string",
                "description": (
                    f"[CHAT] @all text OR [CHAT] @agent_b @agent_c text "
                    f"(1 to {len(AGENT_IDS) - 2} distinct direct recipients); "
                    "use @all to reach everyone; empty for PASS"
                ),
            },
        }
        name = "assistai_communication"
    else:
        available = {
            feature
            for feature, status in observation["features"].items()
            if status["available_now"] and not status["completed"]
        }
        properties = {
            "action_type": {"type": "string", "enum": ["ALLOCATE"]},
            "allocations": {
                "type": "object",
                "properties": {
                    feature: (
                        {"type": "number"}
                        if feature in available
                        else {"type": "number", "enum": [0]}
                    )
                    for feature in FEATURES
                },
                "required": list(FEATURES),
                "additionalProperties": False,
            },
        }
        name = "assistai_allocation"
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


class FirmAgent:
    def __init__(self, agent_id, config):
        self.id = agent_id
        self.cfg = config
        self.client = None
        if not config.mock:
            from openai import AsyncOpenAI

            self.client = AsyncOpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                timeout=90.0,
                max_retries=2,
            )

    async def decide(self, observation):
        if self.cfg.mock:
            if observation["phase"] == "communication":
                if observation["messages_sent_this_week"] == 0:
                    return {
                        "action_type": "CHAT",
                        "message": "[CHAT] @all Let's prioritize prerequisites and finish tasks before splitting time.",
                    }, {
                        "total_tokens": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "cached_tokens": 0,
                        "cost_usd": 0.0,
                    }
                return {"action_type": "PASS"}, {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "cost_usd": 0.0,
                }
            remaining = observation["remaining_hours"]
            open_features = [
                n
                for n, v in observation["features"].items()
                if v["available_now"] and not v["completed"]
            ]
            if not open_features:
                return {"action_type": "ALLOCATE", "allocations": {}}, {
                    "total_tokens": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "cost_usd": 0.0,
                }
            # Use visible cumulative progress; tie-break by effort remaining.
            selected = min(
                open_features,
                key=lambda n: (
                    max(
                        0,
                        FEATURES[n]["hours"]
                        - observation["features"][n]["progress_hours"],
                    ),
                    n,
                ),
            )
            return {
                "action_type": "ALLOCATE",
                "allocations": {selected: round(remaining, 6)},
            }, {
                "total_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cached_tokens": 0,
                "cost_usd": 0.0,
            }

        prompt = PROMPT.replace("{HOURS_PER_WEEK}", f"{self.cfg.hours_per_week:g}")

        response = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": json.dumps(observation, ensure_ascii=False),
                },
            ],
            response_format=response_schema(observation["phase"], observation),
            max_completion_tokens=4096,
        )
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage
        tokens = int(usage.total_tokens) if usage else 0
        input_tokens = int(usage.prompt_tokens) if usage else 0
        output_tokens = int(usage.completion_tokens) if usage else 0
        cached_tokens = (
            int(usage.prompt_tokens_details.cached_tokens or 0)
            if usage and usage.prompt_tokens_details
            else 0
        )
        cost_usd = (
            (input_tokens - cached_tokens) * 0.40
            + cached_tokens * 0.10
            + output_tokens * 1.60
        ) / 1_000_000
        usage_data = {
            "total_tokens": tokens,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cost_usd": cost_usd,
        }
        if choice.finish_reason != "stop" or choice.message.refusal:
            return {
                "action_type": "INVALID",
                "error": (
                    f"finish_reason={choice.finish_reason}; "
                    f"refusal={choice.message.refusal}"
                ),
                "raw_response": content,
            }, usage_data
        action = extract_action(content, phase=observation["phase"])
        if observation["phase"] == "allocation" and action.get("action_type") == "ALLOCATE":
            action["allocations"] = {
                k: v for k, v in action["allocations"].items() if v is not None
            }
        return action, usage_data

    async def update_memory(self, observation, max_words):
        """Write a private rolling summary after the week has closed."""
        empty_usage = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_tokens": 0,
            "cost_usd": 0.0,
        }
        if self.cfg.mock:
            return (
                f"Week {observation['week']}: reviewed firm outcomes and my allocation.",
                empty_usage,
            )
        instruction = (
            f"You are {self.id}. Write private notes of at most {max_words} words "
            "that you may use in future decisions. "
            "Your future observations will independently provide current feature progress, "
            "completion status, customer counts, and available working hours. "
            "Do not store these current-state values or restate the task instructions. "
            "Consider whether any experiences, interactions, expectations, or lessons "
            "are worth retaining beyond the current week. "
            "You may preserve, revise, or discard your previous notes. "
            "Record uncertain interpretations as uncertain, not as facts. "
            "If nothing is worth remembering, return an empty memory. "
            "Do not issue CHAT, PASS, or ALLOCATE actions. "
            "Output the updated memory as JSON."
        )
        response = await self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[
                {"role": "system", "content": instruction},
                {
                    "role": "user",
                    "content": json.dumps(observation, ensure_ascii=False),
                },
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "private_memory_update",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"memory": {"type": "string"}},
                        "required": ["memory"],
                        "additionalProperties": False,
                    },
                },
            },
            max_completion_tokens=600,
        )
        usage = response.usage
        input_tokens = int(usage.prompt_tokens) if usage else 0
        output_tokens = int(usage.completion_tokens) if usage else 0
        cached_tokens = (
            int(usage.prompt_tokens_details.cached_tokens or 0)
            if usage and usage.prompt_tokens_details
            else 0
        )
        usage_data = {
            "total_tokens": int(usage.total_tokens) if usage else 0,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cached_tokens": cached_tokens,
            "cost_usd": (
                (input_tokens - cached_tokens) * 0.40
                + cached_tokens * 0.10
                + output_tokens * 1.60
            ) / 1_000_000,
        }
        choice = response.choices[0]
        if choice.finish_reason != "stop" or choice.message.refusal:
            raise RuntimeError(
                f"Memory update failed for {self.id}: finish_reason={choice.finish_reason}"
            )
        memory = json.loads(choice.message.content)["memory"].strip()
        return " ".join(memory.split()[:max_words]), usage_data