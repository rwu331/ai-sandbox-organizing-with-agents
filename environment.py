"""Authoritative simulator. Agents can never inspect hidden feature payoffs."""
import copy
import math
import random
import re
from schemas import AGENT_IDS, FEATURES, AgentState, Config

HIDDEN_CUSTOMER_GAINS = {
    "feature_1": 45,
    "feature_1_1": 160,
    "feature_1_2": 35,
    "feature_1_3": 210,

    "feature_2": 100,
    "feature_2_1": 40,
    "feature_2_2": 220,
    "feature_2_3": 65,

    "feature_3": 25,
    "feature_3_1": 190,
    "feature_3_2": 110,
    "feature_3_3": 70,

    "feature_4": 80,
    "feature_4_1": 20,
    "feature_4_2": 155,
    "feature_4_3": 260
}


class FirmEnvironment:
    def __init__(self, config: Config):
        self.cfg = config
        self.rng = random.Random(config.seed)
        self.hidden_customer_gains = HIDDEN_CUSTOMER_GAINS.copy()
        self.week = 0
        self.agents = {i: AgentState(i) for i in AGENT_IDS}
        self.progress = {name: 0.0 for name in FEATURES}
        self.completed = set()
        self.customers = 0
        self.cumulative_customer_weeks = 0
        self.history = []
        self.events = []
        self.logs = []
        self.message_history = []
        self.total_tokens = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cached_tokens = 0
        self.total_cost_usd = 0.0
        self._event_no = 0
        self._weekly_spend = {i: {} for i in AGENT_IDS}
        self._communication_stats = {"communication_rounds_used": 0,
            "communication_stop_reason": None}

    def log(self, kind, **fields):
        self._event_no += 1
        event = {"seq": self._event_no, "week": self.week, "type": kind,
            **copy.deepcopy(fields)}
        self.events.append(event)
        return event

    def set_communication_stats(self, rounds_used, stop_reason):
        self._communication_stats = {"communication_rounds_used": rounds_used,
                                     "communication_stop_reason": stop_reason}

    def start_week(self, week):
        self.week = week
        self._communication_stats = {"communication_rounds_used": 0,
            "communication_stop_reason": None}
        self._weekly_spend = {i: {} for i in AGENT_IDS}
        for a in self.agents.values():
            a.remaining_hours = self.cfg.hours_per_week
            a.chat_turns = 0
            a.discussion_done = False
            a.allocated = False
        self.log("week_started", customers=self.customers,
            completed=sorted(self.completed))

    def observe(self, agent_id, phase):
        a = self.agents[agent_id]
        window = self.cfg.history_window
        min_week = 1 if window == -1 else max(1, self.week - window)
        visible_messages = [
            m for m in self.message_history
            if (m["week"] == self.week if window == -2 else m["week"] >= min_week)
            and (m["recipient"] == "all" or m["agent"] == agent_id or agent_id in m["recipients"])
        ]
        # Restrict decision-time attention only. The week-end memory update
        # retains its original inputs, so memory formation is held constant.
        if phase != "memory_update" and self.cfg.attention_capacity >= 0:
            k = self.cfg.attention_capacity
            visible_messages = visible_messages[-k:] if k else []
        observation = {
            "identity": agent_id, "phase": phase, "week": self.week,
            "weeks_total": self.cfg.weeks,
            "goal": "maximize cumulative customer-weeks over eight weeks",
            "remaining_hours": round(a.remaining_hours, 6),
            "send_cost_hours_per_message": round(self.cfg.hours_per_message, 6),
            "receive_cost_hours_per_message": round(
                round(self.cfg.hours_per_message,
                    6) * self.cfg.receive_cost_multiplier, 6
            ),
            "max_message_words": 99,
            "messages_sent_this_week": a.chat_turns,
            "features": {k: {**copy.deepcopy(spec),
                "progress_hours": round(self.progress[k], 6),
                              "remaining_development_hours": round(max(0,
                                  spec["hours"] - self.progress[k]), 6),
                             "completed": k in self.completed,
                             "available_now": all(req in self.completed for req in spec["prerequisites"])}
                         for k, spec in FEATURES.items()},
            "customers": self.customers,
            "cumulative_customer_weeks": self.cumulative_customer_weeks,
            **({"private_memory": a.private_memory} if self.cfg.private_memory else {}),
            "public_events": copy.deepcopy([
                e for e in self.logs if e["type"] != "chat"
                and (window == -2 or e["week"] >= min_week)
            ]),
            "message_history": [
                {
                    "week": m["week"],
                    "round": m.get("round"),
                    "seq": m["seq"],
                    "sender": m["agent"],
                    "recipient": m["recipient"],
                    "channel": "public" if m["recipient"] == "all" else "direct",
                    "recipients": copy.deepcopy(m["recipients"]),
                    "message": m["message"],
                }
                for m in visible_messages
            ],
        }
        return observation

    def account_tokens(self, agent_id, usage):
        tokens = int(usage["total_tokens"])
        self.agents[agent_id].tokens_used += tokens
        self.total_tokens += tokens
        self.total_input_tokens += int(usage["input_tokens"])
        self.total_output_tokens += int(usage["output_tokens"])
        self.total_cached_tokens += int(usage["cached_tokens"])
        self.total_cost_usd += float(usage["cost_usd"])
        self.log("llm_usage", agent=agent_id, tokens=tokens, **{k: v for k,
            v in usage.items() if k != "total_tokens"})

    def chat(self, agent_id, action, round_no=None):
        a = self.agents[agent_id]
        if a.allocated or a.discussion_done:
            return self.log("action_rejected", agent=agent_id,
                reason="discussion_closed")
        if action.get("action_type") != "CHAT":
            return self.log("discussion_pass", agent=agent_id)
        message = str(action.get("message", "")).strip()
        # A direct message may target a proper, nonempty subset of other employees.
        # All recipient tags must appear consecutively at the start of the message.
        # Examples: [CHAT] @agent_b @agent_c Hello / [CHAT] @all Hello
        match = re.match(r"^\[CHAT\]\s+(.+)$", message, re.I | re.S)
        if not match:
            return self.log("action_rejected", agent=agent_id,
                reason="chat_format_must_be_[CHAT]_@target_text")
        rest = match.group(1).strip()
        targets = []
        while True:
            mention = re.match(r"^@([a-z][a-z0-9_]*)\b\s*", rest, re.I)
            if not mention:
                break
            targets.append(mention.group(1).lower())
            rest = rest[mention.end():].lstrip()
        body = rest.lstrip(": ").strip()
        if not targets or not body:
            return self.log("action_rejected", agent=agent_id,
                reason="chat_requires_recipients_and_body")
        if len(targets) != len(set(targets)):
            return self.log("action_rejected", agent=agent_id,
                reason="duplicate_recipient")
        if "all" in targets and len(targets) != 1:
            return self.log("action_rejected", agent=agent_id,
                reason="all_cannot_mix_with_direct_recipients")
        invalid = [rid for rid in targets if rid != "all" and rid not in AGENT_IDS]
        if invalid:
            return self.log("action_rejected", agent=agent_id,
                reason="invalid_recipient", recipients=invalid)
        if agent_id in targets:
            return self.log("action_rejected", agent=agent_id,
                reason="cannot_message_self")
        # A direct message addressing every coworker is a public broadcast.
        public = targets == ["all"] or len(targets) == len(AGENT_IDS) - 1
        target = "all" if public else ",".join(targets)
        recipients = [i for i in AGENT_IDS if i != agent_id] if public else targets
        if public:
            message = f"[CHAT] @all {body}"
        # Count message body only; routing tags and [CHAT] are not message words.
        word_count = len(body.split())
        if word_count >= 100:
            return self.log("action_rejected", agent=agent_id,
                reason="message_too_long", words=word_count, max_words=99)
        # Flat per-message cost, independent of length and recipient count.
        cost = round(self.cfg.hours_per_message, 6)
        receive_cost = round(cost * self.cfg.receive_cost_multiplier, 6)
        if cost > a.remaining_hours + 1e-9:
            return self.log("action_rejected", agent=agent_id,
                reason="insufficient_hours_for_chat", needed_hours=cost,
                    remaining_hours=a.remaining_hours)
        insufficient = [rid for rid in recipients if receive_cost > self.agents[rid].remaining_hours + 1e-9]
        if insufficient:
            return self.log("action_rejected", agent=agent_id,
                reason="recipient_insufficient_hours", recipients=insufficient)
        a.chat_turns += 1
        a.remaining_hours = round(max(0, a.remaining_hours - cost), 6)
        for rid in recipients:
            recipient = self.agents[rid]
            recipient.remaining_hours = round(max(0,
                recipient.remaining_hours - receive_cost), 6)
        event = self.log("chat", agent=agent_id, recipient=target, message=message,
            round=round_no,
                         words=word_count, cost_hours=cost, send_cost_hours=cost,
                         receive_cost_per_agent_hours=receive_cost,
                         total_receive_cost_hours=round(receive_cost * len(recipients),
                             6),
                         total_cost_hours=round(cost + receive_cost * len(recipients),
                             6),
                         recipients=recipients, remaining_hours=a.remaining_hours)
        self.message_history.append(copy.deepcopy(event))
        # Public messages enter public logs. Direct messages are visible only
        # to their sender and specified recipients in message_history.
        if target == "all":
            self.logs.append(event)
        return event

    def allocate(self, agent_id, action):
        a = self.agents[agent_id]
        if a.allocated:
            return self.log("action_rejected", agent=agent_id,
                reason="already_allocated")
        allocations = action.get("allocations", {})
        if not isinstance(allocations, dict):
            return self.log("action_rejected", agent=agent_id,
                reason="allocations_must_be_object")
        # Atomic validation: reject entire malformed allocation; don't spend partial time.
        valid = {}

        for name, raw in allocations.items():
            if name not in FEATURES:
                return self.log("action_rejected", agent=agent_id,
                    reason="unknown_feature", feature=name)

            if isinstance(raw, bool) or not isinstance(raw, (int,
                float)) or not math.isfinite(raw) or raw < 0:
                return self.log("action_rejected", agent=agent_id,
                    reason="invalid_hours", feature=name)

            if raw == 0:
                continue

            if name in self.completed:
                return self.log("action_rejected", agent=agent_id,
                    reason="completed_feature", feature=name)

            if not all(req in self.completed for req in FEATURES[name]["prerequisites"]):
                return self.log("action_rejected", agent=agent_id,
                    reason="prerequisite_not_complete", feature=name)

            valid[name] = round(float(raw), 6)
        total = round(sum(valid.values()), 6)
        tolerance = 0.01

        if total > a.remaining_hours:
            excess = total - a.remaining_hours

            if excess > tolerance + 1e-9:
                return self.log("action_rejected", agent=agent_id,
                    reason="hours_exceeded",
                                requested_hours=total,
                                    remaining_hours=a.remaining_hours)

            for feature in reversed(valid):
                adjustment = min(excess, valid[feature])
                valid[feature] = round(valid[feature] - adjustment, 6)
                excess = round(excess - adjustment, 6)
                if excess <= 0:
                    break

            total = sum(valid.values())
        a.remaining_hours = round(max(0, a.remaining_hours-total), 6)
        a.allocated = True
        a.discussion_done = True
        self._weekly_spend[agent_id] = valid
        # Keep commitments private until all agents have committed.
        self.log("allocation_committed_private", agent=agent_id,
            hours_worked=round(total, 4))
        return {"type": "allocation_accepted", "agent": agent_id}

    def close_week(self):
        # Publish all [ACTION LOG] entries together; order cannot reveal who committed first.
        for agent_id in AGENT_IDS:
            a = self.agents[agent_id]
            allocations = self._weekly_spend[agent_id]
            total = sum(allocations.values())
            for feature, hours in allocations.items():
                self.progress[feature] += hours
            event = self.log("action_log", label="[ACTION LOG]", agent=agent_id,
                             allocations=copy.deepcopy(allocations),
                                 hours_worked=round(total, 4),
                             chat_hours=round(self.cfg.hours_per_week - total - a.remaining_hours, 4),
                             unused_hours=a.remaining_hours)
            self.logs.append(event)
        newly_completed = []
        for name, spec in FEATURES.items():
            if name not in self.completed and self.progress[name] + 0.001 >= spec["hours"]:
                self.completed.add(name)
                newly_completed.append(name)
                # Excess hours were logged as work but do not carry to other features.
                excess_hours = max(0.0, self.progress[name] - spec["hours"])
                self.progress[name] = float(spec["hours"])
                self.customers += self.hidden_customer_gains[name]
                event = self.log("feature_completed", feature=name,
                    customers_gained=self.hidden_customer_gains[name],
                                excess_hours=round(excess_hours, 6))
                self.logs.append(event)
        lost = {}
        for name in FEATURES:
            if name not in self.completed and self.progress[name] > 0:
                fraction = (self.rng.randint(1,
                    99) / 100 if self.cfg.decay_rate == -1 else self.cfg.decay_rate)
                lost[name] = {"percent_outdated": int(fraction * 100),
                              "hours_lost": round(self.progress[name] * fraction, 4)}
                self.progress[name] = round(self.progress[name] * (1-fraction), 6)
        self.cumulative_customer_weeks += self.customers
        row = {"week": self.week, "customers": self.customers,
               "cumulative_customer_weeks": self.cumulative_customer_weeks,
               "new_features": newly_completed,
                   "completed_features": sorted(self.completed),
               "outdated_work": lost, **self._communication_stats}
        self.history.append(row)
        event = self.log("week_ended", **row)
        self.logs.append(event)
        return row

    def final_summary(self):
        return {"weeks_completed": self.week, "customers_at_week_8": self.customers,
                "cumulative_customer_weeks": self.cumulative_customer_weeks,
                "features_completed": sorted(self.completed),
                "total_tokens": self.total_tokens,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "total_cached_tokens": self.total_cached_tokens,
                "total_cost_usd": round(self.total_cost_usd, 6),
                "communication_rounds_per_week": {str(row["week"]): row["communication_rounds_used"] for row in self.history},
                "communication_stop_reasons": {str(row["week"]): row["communication_stop_reason"] for row in self.history},
                "agent_tokens": {k: a.tokens_used for k, a in self.agents.items()}}