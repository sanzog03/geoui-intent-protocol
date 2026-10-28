# Worldview benchmark — GeoUI agent vs VLM baseline on geobench

A re-runnable, verifiable comparison of the two Worldview agents in `demo/worldview/agents`:

- **geoui** — the `worldview-assistant` skill on a bare pydantic-ai agent; renders a
  `GeoIntent` to a Worldview permalink and opens it (browser: navigate + read URL only).
- **vlm** — the non-GeoUI `mio-worldviewagent-v2` skill with full Playwright control;
  clicks and types on the live page and reads `window.location.href` back.

Both run the **same goldens** and are scored by the **same six metrics** (success,
completion, tool / time / token efficiency, turn relevancy; see
[`../harness/README.md`](../harness/README.md)). deepeval's `ConversationSimulator`
plays the user: the first turn of each gold scenario is the verbatim prompt from
`benchmarks/manual/prompts.md` (layer id wording for geoui, searchable-name wording
for vlm, as that suite does on purpose), and the simulated user improvises the
follow-up steps from the scenario text.

## Layout

```
benchmarks/worldview/
├── pyproject.toml              workspace member `geoui-worldview-benchmark` (import `worldview_benchmark`)
├── run.sh                      Chromium + MCP warm-up + `deepeval test run` per agent + summary
├── worldview_benchmark/
│   ├── __init__.py             dataset paths, DEFAULT_BUDGETS (60 s and 20k cache-adjusted tokens per turn)
│   ├── app.py                  WorldviewApp: both agent factories, output→URL, observe(url), discovery tools
│   └── tests/                  offline tests (observe on live VLM URLs, dataset validity)
├── evals/test_worldview.py     the deepeval suite (one test per golden × agent)
├── datasets/
│   ├── gold_dataset.json       Core 1–6 + workflows A/B codified from benchmarks/manual/, with expected state
│   └── synthetic_queries.json  generated with `deepeval generate --method goldens` (see below)
└── results/<run-id>/           one folder per run, committed
    ├── run.json                app, models, versions, git SHA, dataset hashes
    ├── turns.jsonl             one row per agent turn (same fields as the notebook's manual log, plus run context)
    ├── errors.jsonl            tracebacks of error turns
    ├── traces/<conv>/<n>.json  TurnTrace per turn: LLM calls with tokens, tool calls with args/outputs, durations
    ├── conversations.jsonl     transcripts with tool calls and the metric scores
    ├── deepeval/test_run_*.json  deepeval's own result file
    └── summary.json / summary.md
```

## Running

Needs `.env` (see `.env.example`: `OPENAI_API_KEY` plus the plugin's MCP keys), the
`akd-plugins` submodule, Node (`npx`) and `uv sync`.

```bash
BENCHMARK_SMOKE=1 ./benchmarks/worldview/run.sh gold smoke-2026-10-28   # first gold golden, both agents
./benchmarks/worldview/run.sh gold 2026-10-28-gold                       # the full gold set
./benchmarks/worldview/run.sh all  2026-10-28-all geoui                  # one agent only
```

`run.sh` launches (or reattaches to) Chromium on CDP port 9222, warms the remote MCP
servers, runs `deepeval test run` once per agent with `DEEPEVAL_RESULTS_FOLDER`
pointed at the run folder, then writes the summary and scrubs absolute paths. Expect
roughly 15 minutes for the gold set on geoui and 1.5–2.5 hours on vlm (turns of
30 s to 9 minutes, up to 60 tool calls each), plus judge calls.

By hand, one agent per invocation (never `-n`: both agents share one browser tab):

```bash
BENCHMARK_AGENT=vlm BENCHMARK_DATASET=gold BENCHMARK_RUN=2026-10-28-gold \
DEEPEVAL_RESULTS_FOLDER=benchmarks/worldview/results/2026-10-28-gold/deepeval \
uv run deepeval test run benchmarks/worldview/evals/test_worldview.py -k core-4 --identifier 2026-10-28-gold-vlm
```

`-k <golden name>` selects one scenario. Plain `uv run pytest benchmarks/worldview/evals`
would run the agents but write no deepeval result JSON; use `deepeval test run`.

## Reading a run

`summary.md` has one row per scenario × agent with the six scores (✓/✗ at threshold),
turns, tool calls, seconds and cache-adjusted tokens, a **vlm/geoui** ratio row per
scenario, and per-agent totals (pass rates, mean scores, cumulative cost). Every
number can be traced back: `conversations.jsonl` holds the transcript, tool calls and
metric reasons; `traces/` holds the per-turn evidence.

## Verifying a run without rerunning the agents

```bash
uv run python -m geobench.score benchmarks/worldview/results/2026-10-28-gold                     # the deterministic four, no network
uv run python -m geobench.score benchmarks/worldview/results/2026-10-28-gold --metrics all       # also re-judge with gpt-5.2
uv run python -m geobench.summarize benchmarks/worldview/results/2026-10-28-gold
```

The scorer rebuilds every conversation from `conversations.jsonl` + `traces/`, runs
the metrics through `deepeval.evaluate`, replaces the same-named scores and rewrites
the summary. `run.json` records the dataset hashes, so a rerun of `run.sh` on the same
goldens is directly comparable.

## Datasets

**Gold** (`datasets/gold_dataset.json`) codifies `benchmarks/manual/prompts.md` Core 1–6
and `benchmarks/manual/workflows.md` A (with the Terra swap as step 3) and B. Each
golden carries both openers, the ordered follow-up steps in its `scenario`, an
`expected_state`, `checkpoints` for the five-turn workflows, and `max_user_simulations`
(0 for single-shot prompts). Edit the JSON to change what runs; the unit tests
validate it.

**Synthetic** (`datasets/synthetic_queries.json`) is generated from the gold set once,
reviewed, and committed. Synthetic goldens have no openers and no expected state, so
the simulator phrases every turn and only metrics 2–6 run on them:

```bash
uv run deepeval generate --method goldens --variation multi-turn \
  --goldens-file benchmarks/worldview/datasets/gold_dataset.json --num-goldens 16 --model gpt-5.2 \
  --scenario-context "A scientist asking a NASA Worldview assistant to visualise satellite imagery: specific GIBS layers, dates, regions, and refinements such as comparing dates, charting a time series or restyling a layer" \
  --conversational-task "Produce the requested Worldview view and give the user a Worldview URL after each change, asking at most one clarifying question when the dataset is ambiguous" \
  --participant-roles "A domain scientist (user) and the Worldview assistant" \
  --scenario-format "Who the user is, which layer(s), date(s) and region they want, and the follow-up refinements they will ask for, in order" \
  --expected-outcome-format "The final Worldview view the user should end up with, in prose" \
  --output-dir benchmarks/worldview/datasets --file-name synthetic_queries
```

## Budgets

`DEFAULT_BUDGETS` = 60 seconds and 20,000 cache-adjusted tokens per assistant turn,
the same for both agents and for every golden that does not override them. A turn
within budget scores 1.0, a turn at twice the budget 0.5. They are a fixed yardstick,
not derived from either agent's results; the cross-agent comparison is the ratios.

## Gotchas

- Reload nothing: the benchmark does not use the notebook. It does share the Chromium
  on port 9222 with `demo/start.sh`; running both at once will fight over the tab.
- The Playwright MCP is `@playwright/mcp@latest` in the plugin's `.mcp.json`; pin it
  there if runs must be byte-for-byte reproducible.
- deepeval's pytest plugin is blocked in the ordinary unit suite (`-p no:deepeval`);
  `deepeval test run` re-enables it.
