"""randomized sequential discussion; one all-PASS round ends the discusson phase."""
import argparse
import asyncio
import json
import os
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from agent import FirmAgent
from environment import FirmEnvironment
from schemas import AGENT_IDS, FEATURES, Config, normalize_action
from sample_task import TASK
from reporting import save_reports


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def save_results(env, output):
    output.mkdir(parents=True, exist_ok=True)
    write_jsonl(output / "events.jsonl", env.events)
    summary = env.final_summary()
    summary["planned_weeks"] = env.cfg.weeks
    summary = save_reports(output, env.events, env.history, summary)
    (output / "config.json").write_text(json.dumps(asdict(env.cfg), indent=2),
        encoding="utf-8")
    # print("Results:", output)
    # print(json.dumps(summary, indent=2))
    return summary


def get_output_dir(seed):
    runs_dir = Path(os.environ.get("RUNS_DIR", "simulation_outputs"))
    runs_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"{timestamp}_seed{seed}"

    output = runs_dir / base_name
    counter = 1

    while output.exists():
        output = runs_dir / f"{base_name}_{counter}"
        counter += 1

    output.mkdir()
    return output


async def run(config, output):
    env = FirmEnvironment(config)
    agents = {i: FirmAgent(i, config) for i in AGENT_IDS}
    rng = random.Random(config.seed + 10001)
    env.log("task", description=TASK.replace("{HOURS_PER_WEEK}", f"{config.hours_per_week:g}"))

    async def decide(actor, phase, feedback=None, round_no=None):
        observation = env.observe(actor, phase)
        observation["phase"] = "communication" if phase == "discussion" else phase

        if round_no is not None:
            observation["communication_round"] = round_no
            observation["max_communication_rounds"] = config.max_communication_rounds

        if feedback is not None:
            observation["communication_feedback" if phase == "discussion" else "allocation_feedback"] = feedback
        try:
            action, usage = await agents[actor].decide(observation)
        except Exception as exc:
            env.log("api_error", agent=actor, phase=phase, error=repr(exc))
            save_results(env, output)
            raise
        if action.get("action_type") == "INVALID":
            return action, usage
        return normalize_action(action), usage

    for week in range(1, config.weeks + 1):
        env.start_week(week)

        # Randomized sequential discussion; one all-silent round ends communication.
        rounds_used = 0
        stop_reason = "max_rounds_reached"

        for round_no in range(1, config.max_communication_rounds + 1):
            order = list(AGENT_IDS)
            rng.shuffle(order)
            env.log("round_started", round=round_no, order=order)
            messages_this_round = 0

            for position, actor in enumerate(order, 1):
                env.log("activation", agent=actor, phase="discussion", round=round_no,
                    position=position)

                if env.agents[actor].tokens_used >= config.tokens_per_agent or env.total_tokens >= config.max_total_tokens:
                    env.log("discussion_skipped", agent=actor, reason="token_budget")
                    save_results(env, output)
                    raise RuntimeError(f"Token budget exhausted for {actor}; cannot treat this as voluntary silence")

                # Retry invalid discussion actions up to five times.
                feedback = None

                for attempt in range(1, 6):
                    if feedback is not None:
                        env.log("discussion_feedback_sent", agent=actor,
                            round=round_no, attempt=attempt, feedback=feedback)
                    action, usage = await decide(actor, "discussion",
                        feedback=feedback, round_no=round_no)
                    env.account_tokens(actor, usage)

                    if action["action_type"] == "CHAT":
                        event = env.chat(actor, action, round_no=round_no)

                        if event["type"] == "chat":
                            messages_this_round += 1
                            break

                        feedback = {
                            "reason": event.get("reason"),
                            "instruction": (
                                "Your message must contain fewer than 100 words. Please shorten it."
                                if event.get("reason") == "message_too_long"
                                else f"Your message was rejected: {event.get('reason')}. Correct the issue or PASS."
                            )
                        }

                    elif action["action_type"] == "PASS":
                        env.log("discussion_pass", agent=actor)
                        break

                    else:
                        feedback = {
                            "reason": action.get("error", "invalid_action"),
                            "instruction": "Submit a valid CHAT or PASS action."
                        }

                    env.log(
                        "invalid_discussion_action",
                        agent=actor,
                        round=round_no,
                        attempt=attempt,
                        action=action,
                        feedback=feedback
                    )

                if action["action_type"] not in ("CHAT",
                    "PASS") or (action["action_type"] == "CHAT" and event["type"] != "chat"):
                    env.log("discussion_failed", agent=actor, round=round_no,
                        reason="retries_exhausted")
                    save_results(env, output)
                    raise RuntimeError(f"Discussion failed for {actor} after 5 attempts")

                # kind = action["action_type"]
                # print(f"[week {week} round {round_no}] {actor}: {kind}", flush=True)

            rounds_used = round_no
            env.log("round_finished", round=round_no, messages_sent=messages_this_round)

            if messages_this_round == 0:
                stop_reason = "all_silent"
                break

        env.log("communication_ended", rounds_used=rounds_used, reason=stop_reason)
        # print(f"[week {week}] communication ended after {rounds_used} rounds ({stop_reason})", flush=True)
        env.set_communication_stats(rounds_used, stop_reason)

        # Private work allocations; retry invalid or rejected actions up to three times.
        to_allocate = [i for i in AGENT_IDS if not env.agents[i].allocated]

        async def get_allocation(actor):
            observation = env.observe(actor, "allocation")

            if all(f["completed"] for f in observation["features"].values()):
                action = {"action_type": "ALLOCATE", "allocations": {}}
                env.log("allocation_no_work", agent=actor,
                    reason="all_features_completed")
                return env.allocate(actor, action)
            
            feedback = None

            for attempt in range(1, 4):
                if env.agents[actor].tokens_used >= config.tokens_per_agent or env.total_tokens >= config.max_total_tokens:
                    env.log("allocation_failed", agent=actor, reason="token_budget",
                        attempt=attempt)
                    return None

                if feedback is not None:
                    env.log(
                        "allocation_feedback_sent",
                        agent=actor,
                        attempt=attempt,
                        feedback=feedback,
                    )
                action, usage = await decide(actor, "allocation", feedback)
                env.account_tokens(actor, usage)
                env.log("allocation_response", agent=actor, attempt=attempt,
                    action=action)

                if action.get("action_type") != "ALLOCATE" or not isinstance(action.get("allocations"), dict):
                    env.log("invalid_allocation_action", agent=actor, attempt=attempt,
                        action=action)
                    feedback = {"reason": "invalid_action",
                        "instruction": "Submit an ALLOCATE action containing an allocations dictionary."}
                    continue

                # Reject malformed hours rather than silently discarding them.
                from math import isfinite
                if any(not isinstance(hours, (int, float)) or isinstance(hours,
                    bool) or not isfinite(hours) or hours < 0 for hours in action["allocations"].values() if hours is not None):
                    env.log("invalid_allocation_action", agent=actor, attempt=attempt,
                        action=action, reason="invalid_hours")
                    feedback = {"reason": "invalid_hours",
                        "instruction": "All allocated hours must be finite, nonnegative numbers."}
                    continue

                action["allocations"] = {feature: hours for feature,
                    hours in action["allocations"].items() if hours is not None and hours > 0}
                outcome = env.allocate(actor, action)

                if outcome["type"] != "action_rejected":
                    return outcome

                env.log("allocation_rejected", agent=actor, attempt=attempt,
                    action=action, outcome=outcome)

                reason = outcome.get("reason")
                available_features = [
                    name for name, spec in FEATURES.items()
                    if name not in env.completed
                    and all(req in env.completed for req in spec["prerequisites"])
                ]

                if reason in ("completed_feature", "prerequisite_not_complete"):
                    instruction = (
                        f"Your allocation to {outcome['feature']} was rejected because "
                        "the feature is not eligible for work. "
                        f"Currently available, incomplete features: {available_features}. "
                        "Allocate positive hours only to eligible features."
                    )
                elif reason == "hours_exceeded":
                    instruction = (
                        f"Your allocation exceeds your remaining budget of "
                        f"{outcome['remaining_hours']:.6f} hours. "
                        "Reduce your total allocated hours to fit within this budget."
                    )
                else:
                    instruction = "Correct the reported allocation constraint violation."

                feedback = {
                    "reason": reason,
                    "details": {
                        key: value for key, value in outcome.items()
                        if key not in ("type", "seq", "week", "agent")
                    },
                    "previous_allocation": action["allocations"],
                    "instruction": instruction,
                }

            env.log("allocation_failed", agent=actor, reason="retries_exhausted")
            return None

        # Collect allocations concurrently; commitments remain private until week end.
        outcomes = await asyncio.gather(*(get_allocation(actor) for actor in to_allocate))
        failures = [actor for actor, outcome in zip(to_allocate,
            outcomes) if outcome is None]

        if failures:
            save_results(env, output)
            raise RuntimeError(f"Allocation failed for {failures}; refusing to record technical failures as zero-hour work")


        result = env.close_week()

        if config.private_memory:
            # After final accepted allocations AND public week-end outcomes.
            # All updates use the same completed-week snapshot.
            async def update_one_memory(actor):
                observation = env.observe(actor, "memory_update")
                observation["own_allocation"] = env._weekly_spend[actor].copy()
                try:
                    memory, usage = await agents[actor].update_memory(observation,
                        config.memory_max_words)
                    return actor, memory, usage
                except Exception as exc:
                    env.log("memory_update_failed", agent=actor, error=repr(exc))
                    raise

            try:
                updates = await asyncio.gather(*(update_one_memory(actor) for actor in AGENT_IDS))
            except Exception:
                save_results(env, output)
                raise
            for actor, memory, usage in updates:
                env.account_tokens(actor, usage)
                old_memory = env.agents[actor].private_memory
                env.agents[actor].private_memory = memory
                # Researcher-only log, not added to public_events or message_history.
                env.log("private_memory_updated", agent=actor, old_memory=old_memory,
                    memory=memory, words=len(memory.split()))

        save_results(env, output)

        messages = sum(e["type"] == "chat" and e["week"] == week for e in env.events)

        print(
            f"W{week}/{config.weeks} | "
            f"rounds={rounds_used} | "
            f"msgs={messages} | "
            f"customers={result['customers']} | "
            f"CW={result['cumulative_customer_weeks']} | "
            f"new={len(result['new_features'])}",
            flush=True
        )

    return env


def main():
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(description="AssistAI fully sequential communication simulation")
    parser.add_argument("--mock", action="store_true", help="Run without API calls")
    parser.add_argument("--weeks", type=int, default=8)
    parser.add_argument("--hours-per-week", type=float, default=40.0,
        help="Working hours available to each agent per week (default: 40)")
    parser.add_argument("--max-communication-rounds", "--communication-rounds",
        dest="max_communication_rounds", type=int, default=3,
            help="Safety cap; one all-silent round stops earlier")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL",
        "gpt-4.1-mini"))
    parser.add_argument("--hours-per-message", type=float, default=0.25)
    parser.add_argument("--receive-cost-multiplier", type=float, default=0.5)
    parser.add_argument("--tokens-per-agent", type=int, default=10000000)
    parser.add_argument("--max-total-tokens", type=int, default=50000000)
    parser.add_argument("--history-window", type=int, default=-2,
        help="-2=original behavior (current-week messages, all public events); -1=full history; 0=current week; N=last N previous weeks plus current")
    parser.add_argument("--attention-capacity", type=int, default=5,
        help="-1=all messages; 0=no messages; K=last K visible messages at decision time")
    parser.add_argument("--private-memory", action="store_true",
        help="Enable one private rolling memory update per agent after each week")
    parser.add_argument("--memory-max-words", type=int, default=150)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--decay-rate", type=float, default=-1,
        help="Knowledge decay rate: -1=random (1%-99%), 0-1=fixed rate")
    args = parser.parse_args()
    if args.hours_per_week <= 0:
        parser.error("--hours-per-week must be positive")

    if args.decay_rate != -1 and not 0 <= args.decay_rate <= 1:
        parser.error("--decay-rate must be -1 or between 0 and 1")

    if not 1 <= args.weeks <= 8 or args.max_communication_rounds < 1 or args.hours_per_message < 0 or args.receive_cost_multiplier < 0 or args.tokens_per_agent < 1 or args.max_total_tokens < 1 or args.history_window < -2 or args.attention_capacity < -1 or args.memory_max_words < 1:
        parser.error("Invalid week count, communication cost, or safety limits")

    cfg = Config(weeks=args.weeks, hours_per_week=args.hours_per_week,
        max_communication_rounds=args.max_communication_rounds, seed=args.seed, 
                 model=args.model, mock=args.mock, 
                 hours_per_message=args.hours_per_message,
                     receive_cost_multiplier=args.receive_cost_multiplier, 
                 tokens_per_agent=args.tokens_per_agent,
                     max_total_tokens=args.max_total_tokens,
                 history_window=args.history_window,
                     attention_capacity=args.attention_capacity, 
                 private_memory=args.private_memory,
                     memory_max_words=args.memory_max_words,
                 decay_rate=args.decay_rate,)

    if not cfg.mock and not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY in .env or run with --mock")


    output = args.output_dir if args.output_dir else get_output_dir(cfg.seed)
    output.mkdir(parents=True, exist_ok=True)
    print(f"START | seed={cfg.seed} | model={cfg.model} | {output}", flush=True)

    try:
        env = asyncio.run(run(cfg, output))
    except Exception:
        print(f"FAILED | seed={cfg.seed} | {output}", flush=True)
        raise

    summary = save_results(env, output)
    print(
        f"DONE | seed={cfg.seed} | "
        f"CW={summary['cumulative_customer_weeks']} | "
        f"features={len(summary['features_completed'])} | "
        f"tokens={summary['total_tokens']} | cost=${summary['total_cost_usd']:.4f} | "
        f"{output}",
        flush=True
    )



if __name__ == "__main__":
    main()