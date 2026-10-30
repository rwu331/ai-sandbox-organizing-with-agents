# AI Sandbox: Organizing with Agents

This repository provides **AI Sandbox**, a configurable multi-agent simulation framework for studying how organizational behavior and structure emerge when autonomous AI agents work toward a shared objective. Researchers can systematically vary experimental conditions—including working hours, access to past messages, communication costs, and knowledge decay—and examine their effects on communication patterns, emergent informal authority, and organizational performance.

In the default scenario, **10 equal-status AI agents** act as employees of a startup over **8 simulated weeks**. Each week, they exchange messages and independently decide how to allocate their working hours among product-development tasks. Features have prerequisites, and completing a feature attracts customers. The firm's objective is to **maximize cumulative customers**, calculated by adding the customer count at the end of each week. Messages consume working time, so communication and development compete for the same resources.

**To reproduce the pilot experiments:** See [`pilot_experiments/README.md`](pilot_experiments/README.md) for the original experiment settings, archived results, and commands to rerun the hours, memory (attention-capacity), and communication-cost pilots. **This README is a general guide to using the sandbox**.

## 1. Repository structure

The main files are organized by their role in the research workflow:

| File or folder | Purpose |
| --- | --- |
| `runner.py` | Starts a simulation, coordinates the weekly decision process, and saves run outputs |
| `agent.py` | Calls the LLM for agents' communication, allocation, and optional private-memory decisions; also provides mock agents for testing |
| `environment.py` | Applies simulation rules, tracks available hours and feature progress, and records events and outcomes |
| `schemas.py` | Defines configuration defaults, agent identifiers, feature requirements, and basic action validation |
| `sample_task.py` | Defines the high-level task description recorded in each run's event log |
| `prompts/peer_agent.md` | Contains the instructions given to LLM agents, including the business setting, rules, and action format |
| `response_parser.py` | Parses and validates agent responses |
| `reporting.py` | Produces the per-run summary and weekly agent/firm reports |
| `generate_comparison.py` | Combines results from multiple runs into a comparison table |
| `hierarchy_metrics.py` | Uses a separate LLM evaluator to classify attempts to exercise authority in agent messages |
| `pilot_experiments/` | Archived pilot runs, aggregate outputs, and a separate reproduction guide |
| `requirements.txt` | Python packages needed to run the code |

For most experiments, begin with `runner.py` and adjust its command-line options. The other files implement the simulation rules, agent instructions, and analysis pipeline.

## 2. Setup

Run the following commands in a terminal from the repository's root folder. You need Python 3 and an OpenAI API key for simulations involving LLM agents.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a local `.env` file from the provided example:

```bash
cp .env.example .env
```

Then replace the placeholder API key in `.env` with your own:

```text
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4.1-mini
```

Do not commit `.env` or API credentials to GitHub. The provided `.env.example` can remain in the repository. To test the code without an API key or API charges, use `--mock` as explained below.

## 3. Run a simulation

Run a simulation with the default settings:

```bash
python3 runner.py
```

For a quick, no-API test, run just one week with rule-based mock agents:

```bash
python3 runner.py --mock --weeks 1
```

Mock agents follow simple predefined rules rather than making LLM decisions. This is useful for checking that the simulation runs correctly, **not** for drawing research conclusions about LLM organizational behavior.

To change a setting, add an option to the command. For example, this simulation gives each agent 20 hours per week and limits them to the three most recent visible messages:

```bash
python3 runner.py --hours-per-week 20 --attention-capacity 3
```

By default, each simulation creates its own timestamped folder in `simulation_outputs/`. To choose a location yourself:

```bash
python3 runner.py --seed 42 --output-dir simulation_outputs/example_seed42
```

Each run contains five files:

| File | What it contains |
| --- | --- |
| `config.json` | Settings used in the simulation |
| `events.jsonl` | Chronological record of messages, decisions, and simulation events |
| `summary.json` | Overall outcomes and resource-use totals |
| `agent_week.csv` | Weekly activity and resource use for each agent |
| `firm_week.csv` | Weekly firm performance and communication measures |

An interrupted or failed run may contain only partial records.

### API usage and cost

LLM simulations use paid API calls. During a simulation, the terminal displays weekly progress. After a successful run, it prints a summary including cumulative customers, completed features, total tokens used, and estimated API cost.

For example:

```text
DONE | seed=42 | CW=2105 | features=5 | tokens=3248742 | cost=$0.9861 | simulation_outputs/example_seed42
```

The estimated cost is also saved as `total_cost_usd` in each run's `summary.json`. Token usage and cost are tracked from the model's reported input, cached input, and output tokens.

The cost estimate uses pricing configured in `agent.py` for `gpt-4.1-mini`. If using another model or if API prices change, update the pricing constants to obtain an accurate estimate. Actual billed costs may differ.

Mock simulations (`--mock`) do not make API calls and report zero API cost. Separate hierarchy evaluation using `hierarchy_metrics.py` may incur additional API charges.

## 4. Change simulation settings

The following options can be passed to `runner.py`. If an option is omitted, its default is used.

**Note:** The sandbox is designed for an eight-week research scenario. Shorter runs are supported for testing, but some task descriptions and comparison measures assume eight weeks.

| Option | Default | Valid values | Description |
| --- | --- | --- | --- |
| `--weeks` | `8` | Integers 1–8 | Number of simulated weeks |
| `--hours-per-week` | `40` | Positive numbers | Working hours available to each agent per week |
| `--max-communication-rounds` | `3` | Positive integers | Maximum rounds of discussion each week; discussion ends earlier if everyone passes in a round |
| `--hours-per-message` | `0.25` | Nonnegative numbers | Hours paid by the sender of a message |
| `--receive-cost-multiplier` | `0.5` | Nonnegative numbers | Recipient cost relative to the sending cost (default: 0.125 hours per recipient) |
| `--attention-capacity` | `5` | `-1` or integers ≥ 0 | Number of recent visible messages available when making a decision; `-1` means no additional cap, `0` means none |
| `--history-window` | `-2` | `-2`, `-1`, or integers ≥ 0 | How far back message and public-event history extends; explained below |
| `--private-memory` | Off | Flag (on/off) | Allow agents to maintain private summaries between weeks |
| `--memory-max-words` | `150` | Positive integers | Word limit for each private summary when private memory is enabled |
| `--decay-rate` | `-1` | `-1` or numbers from 0 to 1 | Fraction of unfinished progress lost at week-end; `-1` samples randomly from 1% to 99%, while `0`–`1` specifies a fixed fraction |
| `--seed` | `42` | Integers | Seed for simulation randomness |
| `--model` | `gpt-4.1-mini` | Supported model identifiers | Model used for LLM agents (also configurable using `OPENAI_MODEL`) |
| `--tokens-per-agent` | `10000000` | Positive integers | Per-agent token limit |
| `--max-total-tokens` | `50000000` | Positive integers | Overall token limit |
| `--mock` | Off | Flag (on/off) | Use rule-based agents without API calls |
| `--output-dir` | Automatic | Valid directory path | Save outputs in a specified folder |

**Message history and memory are different settings.** 
- `--history-window` controls which past messages and public events are eligible to appear in an observation: `-2` retains current-week messages and all historical public events (the original behavior); `-1` includes messages from all weeks; `0` includes current-week messages; and a positive value `N` includes the current week plus the preceding `N` weeks. 
- Within that visible history, `--attention-capacity K` restricts decision-time access to the most recent `K` messages. The default is `5`; `-1` removes this additional cap.
- `--private-memory` instead enables an agent-written private summary updated after each week.

### Changing the broader scenario

By default, the sandbox uses 10 agents and a workload scale of 2. These are set through the environment variables `ASSISTAI_NUM_AGENTS` (supported values: 5 or 10) and `ASSISTAI_WORKLOAD_SCALE`, rather than command-line options.

**Check the agent instructions if you change the underlying task.** The prompt in `prompts/peer_agent.md` and the logged task description in `sample_task.py` describe an eight-week startup scenario with 16 features across four branches. The prompt also contains illustrative examples based on a 40-hour workweek. The configured weekly hour limit is inserted automatically, so changing `--hours-per-week` alone does not require editing the prompt. However, if you change the number of weeks, feature structure, or other fundamental task assumptions, review these descriptions and examples to ensure they remain consistent with the simulation rules in `schemas.py` and `environment.py`. The comparison script also currently assumes eight weeks when assigning completion status.

### Example experiments

**Reduce weekly work hours:**

```bash
python3 runner.py --hours-per-week 10
```

**Constrain message access and enable private summaries:**

```bash
python3 runner.py --attention-capacity 3 --private-memory --memory-max-words 150
```

**Increase the cost of receiving messages:**

```bash
python3 runner.py --receive-cost-multiplier 0.8
```

**Use a fixed 50% progress-decay rate instead of random decay:**

```bash
python3 runner.py --decay-rate 0.5
```

## 5. Compare multiple runs

To compare experimental conditions, save each simulation in a separate folder with the format `<experiment>_<value>_seed<seed>`. The comparison script reads these names to identify treatment values; it does not infer treatment labels from the saved configurations.

For example:

```bash
ROOT="simulation_outputs/memory_experiment"
for capacity in -1 1 3 5 10 15; do
  python3 runner.py --seed 562 --attention-capacity "$capacity" \
    --output-dir "$ROOT/memory_${capacity}_seed562"
done
python3 generate_comparison.py "$ROOT"
```

The resulting `comparison.csv` contains one row per simulation, with the following measures:

| Category | Measure | Description |
| --- | --- | --- |
| Experimental information | `experiment` | Name of the experimental condition |
| | `value` | Treatment value |
| | `seed` | Simulation random seed |
| | `status` | Whether the simulation completed all eight weeks |
| | `weeks_completed` | Number of simulated weeks completed |
| Firm performance | `final_customers` | Number of customers at the end of the simulation |
| | `cumulative_customers` | Sum of customer counts at the end of each week |
| | `explored_branches` | Number of development branches receiving positive work allocations |
| Communication | `total_msg_sent` | Total number of messages sent |
| | `total_msg_received` | Total number of individual message deliveries to recipients |
| | `direct_msg` | Number of direct (non-public) messages |
| | `zero_msg_weeks` | Number of completed weeks with no messages |
| | `total_chat_words` | Total words in sent messages |
| | `total_chat_hours` | Total working hours spent sending and receiving messages |
| Resource allocation | `total_work_hours` | Total hours allocated to feature development |
| | `total_underallocated_hours` | Total unused working hours |
| | `total_overallocated_hours` | Total hours allocated beyond completed features' requirements |
| | `allocation_rejections` | Number of rejected allocation attempts |
| Computational usage | `total_tokens` | Total LLM tokens consumed during the simulation |

The script calculates these measures from each run's `events.jsonl` file. Existing per-run reports do not need to be regenerated.

**Note:** `status` currently uses an eight-week completion criterion. For shorter simulations, `weeks_completed` provides the actual number of completed weeks.

## 6. Measure emergent authority

The sandbox can separately analyze agents' messages using an LLM-based evaluator. It classifies whether each message **attempts to exercise informal authority**—for example, by directing other agents' work—rather than simply contributing to a peer discussion. This analysis is performed **after the simulation** and does not affect agents' decisions.

First create `comparison.csv` as shown above, then run:

```bash
python3 hierarchy_metrics.py simulation_outputs/hours_experiment --model gpt-4.1-mini
```

This creates `comparison_with_hierarchy.csv` with three additional measures:

| Measure | Description |
| --- | --- |
| `authority_msg` | Number of messages classified as attempts to exercise authority |
| `authority_agents` | Number of distinct agents sending at least one such message |
| `first_week_hierarchy` | First week containing an authority-classified message, if any |

The evaluator also saves `hierarchy_assessments.jsonl` for reviewing individual judgments. These metrics describe **authority expressed in communication**, not verified obedience, effective leadership, or a stable hierarchy. Running the evaluator uses API calls and may produce different classifications on repeated assessments.

## 7. Reproducibility and research use

- **Use the pilot-specific guide for replication.** See [`pilot_experiments/README.md`](pilot_experiments/README.md) for the conditions used in the archived studies and how to reanalyze their saved events.
- **Save configurations and logs.** Retain `config.json`, `events.jsonl`, output tables, model identifiers, and the code version used for each experiment.
- **Interpret seeds carefully.** Seeds control local random processes such as speaking order and progress decay, but do not guarantee identical LLM responses or final outcomes. A different sequence of agent decisions may also change which random draws are used.
- **Distinguish simulations from post-processing.** `generate_comparison.py` reconstructs metrics from event logs; `hierarchy_metrics.py` makes additional LLM-based judgments that can vary between evaluations.
- **Account for API costs.** Full LLM simulations and hierarchy evaluation may incur charges. `--mock` is for checking the code, not reproducing behavioral findings.
