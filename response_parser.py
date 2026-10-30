"""Parse and validate AssistAI actions, preserving technical failures for logging."""
import json
import math
from schemas import FEATURES, normalize_action


def extract_action(text: str, phase=None) -> dict:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        action = json.loads(cleaned)
    except (ValueError, TypeError):
        return {"action_type": "INVALID", "error": "Malformed JSON",
            "raw_response": cleaned}
    if not isinstance(action, dict):
        return {"action_type": "INVALID", "error": "Response is not an object",
            "raw_response": cleaned}
    kind = action.get("action_type")
    if phase == "communication":
        if kind not in ("CHAT", "PASS"):
            return {"action_type": "INVALID",
                "error": "Communication requires CHAT or PASS", "raw_response": cleaned}
        if kind == "CHAT" and (not isinstance(action.get("message"),
            str) or not action["message"].startswith("[CHAT] @")):
            return {"action_type": "INVALID", "error": "Invalid chat message",
                "raw_response": cleaned}
    elif phase == "allocation":
        if kind != "ALLOCATE" or not isinstance(action.get("allocations"), dict):
            return {"action_type": "INVALID",
                "error": "Allocation requires allocations object",
                    "raw_response": cleaned}
        for feature, hours in action["allocations"].items():
            if feature not in FEATURES or (hours is not None and (isinstance(hours,
                bool) or not isinstance(hours, (int,
                    float)) or not math.isfinite(hours) or hours < 0)):
                return {"action_type": "INVALID", "error": "Invalid feature or hours",
                    "raw_response": cleaned}
    elif kind not in ("CHAT", "PASS", "ALLOCATE"):
        return {"action_type": "INVALID", "error": "Unknown action type",
            "raw_response": cleaned}
    return normalize_action(action)