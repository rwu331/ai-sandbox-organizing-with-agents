# Pilot Experiments

This directory contains archived runs from three pilots of **AI Sandbox: Organizing with Agents**. Each pilot varies one parameter while holding the others fixed. The commands below use the current repository code to **rerun the corresponding experimental conditions**; they create new results under `simulation_outputs/` without changing the archive.

Run commands from the repository root after installing `requirements.txt` and setting `OPENAI_API_KEY`. All three pilots use **10 agents, 8 weeks, workload scale 2.0, `gpt-4.1-mini`, 0.25 sending hours per message, randomly sampled decay (1%–99%), and token limits of 10,000,000 per agent / 50,000,000 overall**. Private memory is **enabled only in the attention-capacity pilot**. The commands explicitly specify settings that differ from the current defaults; remaining settings follow the current defaults, consistent with the corresponding historical behavior as explained below.

## 1. Rerun the pilot conditions

### Weekly work hours

Vary `hours_per_week` from 10 to 100; seed 42, 10 communication rounds, receiving-cost multiplier 0.5, unlimited attention capacity (-1), and private memory off.

```bash
ROOT="simulation_outputs/experiments_hours"
for hours in 10 20 30 40 50 60 70 80 90 100; do
  python3 runner.py --seed 42 --hours-per-week "$hours" \
    --max-communication-rounds 10 --attention-capacity -1 \
    --output-dir "$ROOT/hours_${hours}_seed42"
done
python3 generate_comparison.py "$ROOT"
```

### Bounded rationality (attention capacity)

Vary `attention_capacity` from unlimited (-1) to the 1–15 most recent visible messages; seed 562, 3 communication rounds, 40 hours per agent per week, receiving-cost multiplier 0.5, private memory on (limited to 150 words).

```bash
ROOT="simulation_outputs/experiments_memory"
for capacity in -1 $(seq 1 15); do
  python3 runner.py --seed 562 --attention-capacity "$capacity" \
    --max-communication-rounds 3 --hours-per-week 40 \
    --receive-cost-multiplier 0.5 \
    --history-window -2 --private-memory --memory-max-words 150 \
    --output-dir "$ROOT/memory_${capacity}_seed562"
done
python3 generate_comparison.py "$ROOT"
python3 hierarchy_metrics.py "$ROOT" --model gpt-4.1-mini
```

### Communication cost

Vary the `receiving-cost-multiplier` from 0.00 to 1.00 in steps of 0.01; seed 42, 10 communication rounds, 40 hours per agent per week, unlimited attention capacity (-1), and private memory off. The sending cost remains 0.25 hours per message.

```bash
ROOT="simulation_outputs/experiments_ratio"
for i in $(seq 0 100); do
  ratio=$(awk -v i="$i" 'BEGIN {printf "%.2f", i/100}')
  python3 runner.py --seed 42 --receive-cost-multiplier "$ratio" \
    --max-communication-rounds 10 --hours-per-week 40 \
    --attention-capacity -1 \
    --output-dir "$ROOT/ratio_${ratio}_seed42"
done
python3 generate_comparison.py "$ROOT"
python3 hierarchy_metrics.py "$ROOT" --model gpt-4.1-mini
```

## 2. Archived results and reanalysis

```text
pilot_experiments/
├── experiments_hours/
│   ├── hours_10_seed42/ ... hours_100_seed42/
│   └── output_hours.csv
├── experiments_memory/
│   ├── memory_-1_seed562/ ... memory_15_seed562/
│   └── output_memory.csv
└── experiments_ratio/
    ├── ratio_0.00_seed42/ ... ratio_1.00_seed42/
    └── output_ratio.csv

Each run directory contains:
├── config.json       # Recorded simulation settings
├── events.jsonl      # Chronological event log
├── summary.json      # Run-level summary
├── agent_week.csv    # Weekly agent measures
└── firm_week.csv     # Weekly firm measures
```

The archived `output_*.csv` files contain the original aggregated pilot results. The memory and ratio outputs also include LLM-coded authority measures; the hours output does not.

Recompute comparison metrics **from the archived event logs**, without rerunning the simulations:

```bash
python3 generate_comparison.py pilot_experiments/experiments_hours
python3 generate_comparison.py pilot_experiments/experiments_memory
python3 generate_comparison.py pilot_experiments/experiments_ratio
```

This writes a new `comparison.csv` in each experiment folder without overwriting `output_*.csv`. To rerun LLM-based hierarchy coding on archived messages:

```bash
python3 hierarchy_metrics.py pilot_experiments/experiments_memory --model gpt-4.1-mini
python3 hierarchy_metrics.py pilot_experiments/experiments_ratio --model gpt-4.1-mini
```

These commands write `comparison_with_hierarchy.csv` and evaluator records. New LLM judgments may differ from the archived measures.

## 3. Historical configuration compatibility

The pilot experiments were conducted during the development of the AI Sandbox, with incremental updates to configuration and reporting. The core simulation framework remained consistent across the pilots. Parameters not recorded in earlier config.json were verified against the historical implementation and are explicitly specified above where they differ from current defaults, allowing the commands to reproduce the original experimental conditions.

**Reproducibility:** Matching experimental conditions and seeds does not guarantee identical historical LLM trajectories or measurements, as model responses, prompts, code versions, and hierarchy evaluations may differ. The archived event logs and `output_*.csv` files preserve the original pilot results. Full reruns incur API costs; `--mock` is intended for testing rather than research replication.