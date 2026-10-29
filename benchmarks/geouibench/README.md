# geouibench — the utilities and how to use them

`geouibench` is the benchmark utility: it simulates a multi-turn user with
deepeval, traces every agent turn, scores each conversation on six outcome-first
metrics, generates synthetic goldens, re-scores committed runs offline, and
compares agent kinds. It names no application; an application is a directory with
an `app.py` (the contract is in `app.py` here, the on-disk convention in
`appdir.py`). For the design, the dataset format and the metric definitions see
[`../README.md`](../README.md); this file is the module-by-module reference.

Install: it is a workspace member, so `uv sync` from the repo root is enough. Keys
for the judge and simulator model (`OPENAI_API_KEY`) come from `.env`.

## The command line (`cli.py`)

Everything a benchmark author needs is on `python -m geouibench`:

```bash
uv run python -m geouibench run       benchmarks/<app> gold [synthetic ...|all] [--run-id ID] [--agent KIND ...] [--smoke]
uv run python -m geouibench score     benchmarks/<app>/results/<run-id> [--metrics all|success,tool,time,token,completion,relevancy] [--model NAME]
uv run python -m geouibench summarize benchmarks/<app>/results/<run-id> [--reference KIND]
uv run python -m geouibench synthetic benchmarks/<app> [--gold NAME] [--out NAME] [--model NAME] [--work-dir DIR]
uv run python -m geouibench datasets  benchmarks/<app>
```

| command | what happens |
|---|---|
| `run` | loads the app, calls its optional `prepare()` (returned variables join the environment), writes `run.json`, runs `deepeval test run` on `evals/test_benchmark.py` once per agent kind in order (never in parallel: kinds may share a browser), then writes `summary.json` / `summary.md`. Exit status 1 when deepeval reported threshold failures for any kind. `--smoke` keeps the first golden of each dataset and allows one extra user turn. |
| `score` | rebuilds every conversation from `conversations.jsonl` and `traces/`, runs the chosen metrics through `deepeval.evaluate`, replaces the same-named scores and rewrites the summary. The default four are deterministic and need no network; `completion` and `relevancy` call the judge. |
| `summarize` | recomputes the rows, ratios and totals and scrubs absolute paths out of every text artifact. |
| `synthetic` | gold dataset → one context per golden → `deepeval generate --method contexts --variation multi-turn` with the app's `SYNTHETIC_STYLE` → prepared dataset in `datasets/<out>.json` (default `synthetic_queries`). Review before committing. |
| `datasets` | lists `datasets/*.json` by name. |

Dataset names resolve to `datasets/<name>.json` or the one file whose stem starts
with the name; `all` is every dataset.

## The Python API, by module

### `app.py` — the contract

```python
from geouibench import BenchmarkApp, Budgets

class MyApp:                                   # satisfies BenchmarkApp (a runtime-checkable Protocol)
    name = "myapp"
    agent_kinds = ("protocol", "browser")      # the first kind is the reference for ratios
    auto_layers = frozenset({"Coastlines"})    # layers the app adds by itself
    discovery_tools = frozenset({"search"})    # calls that are waste on fully specified prompts
    budgets = Budgets(seconds_per_turn=60, tokens_per_turn=20_000)

    def build_agent(self, kind, *, cdp_endpoint, extra_capabilities): ...  # pydantic-ai Agent; pass extra_capabilities through
    def chatbot_role(self, kind) -> str: ...
    def output_url(self, output) -> str | None: ...
    def observe(self, url) -> UIState: ...     # GeoIntent of what the URL shows; ValueError if unparseable
    def prepare(self) -> dict[str, str]: ...   # optional: setup before a run, returns env for the benchmark processes

APP = MyApp()
```

`prepare_app(app)` runs the hook when present and returns `{}` otherwise.

### `appdir.py` — app directories

```python
from geouibench import load_app_dir

app_dir = load_app_dir("benchmarks/worldview")   # imports <dir>/app.py by path, validates APP
app_dir.app                                      # the BenchmarkApp
app_dir.datasets()                               # {"gold_dataset": Path, "synthetic_queries": Path}
app_dir.dataset("gold")                          # datasets/gold_dataset.json (exact name or unique prefix)
app_dir.select_datasets(["gold", "synthetic"])   # {"gold": Path, "synthetic": Path}; "all" for everything
app_dir.run_dir("2026-10-28-gold")               # <dir>/results/2026-10-28-gold
app_dir.synthetic_style                          # the module's SYNTHETIC_STYLE, or None
```

`AppDirError` says what is missing. Two directories with the same basename load
as distinct modules.

### `datasets.py` — goldens and their metadata

```python
from geouibench.datasets import validate_dataset, goldens_for, dataset_hash, GoldenMeta, Budgets

rows = validate_dataset(path, agent_kinds=app.agent_kinds)        # [(ConversationalGolden, GoldenMeta)]; DatasetError on problems
goldens = goldens_for(path, "protocol", agent_kinds=app.agent_kinds, default_budgets=app.budgets)
                                                                    # opener injected as the first user Turn, budgets filled, agent_kind + dataset added
dataset_hash(path)                                                  # sha256 of the canonical JSON, recorded in run.json
```

`GoldenMeta` is the typed view of `additional_metadata` (`openers`, `expected_state`,
`checkpoints`, `max_user_simulations`, `state_threshold`, `fully_specified`,
`budgets`; `is_gold` is true when an expected state exists).

### `state.py` — the state judge

```python
from geouibench.state import ExpectedState, compare_state, checkpoint_reached, judge_url

expected = ExpectedState(layers={"MODIS_Aqua_Aerosol_Optical_Depth_3km": None}, time="2025-09-15")
match = compare_state(app.observe(url), expected, auto_layers=app.auto_layers)   # StateMatch(matched, missed, score)
checkpoint_reached(state, ExpectedState(layers={"X": None}), auto_layers=app.auto_layers)   # bool
judge_url(app, url_or_none, expected)        # same as compare_state, but None / unparseable URLs score 0 with an error
```

Layers are judged present-and-visible with opacity (`None` means "do not check");
`time` as a UTC date; `crs`; and the `compare`, `chart` and `styling` extension
fields. Viewport bounds are never judged.

### `tracing.py` — one deepeval trace per turn

```python
from geouibench.tracing import tracing_capability, traced_turn, save_trace, load_trace

agent = app.build_agent(kind, cdp_endpoint=None, extra_capabilities=[tracing_capability()])
run = await traced_turn(agent, "render A", message_history=[], thread_id="conv-1")
run.result, run.error            # the pydantic-ai result, or the exception (never raised)
run.trace                        # TurnTrace: llm_calls (tokens, durations), tool_calls (args, outputs), usage, error
save_trace(run.trace, path); load_trace(path)
```

`traced_turn` resets deepeval's trace context around the call, so consecutive turns
on one loop get separate traces, and marks the trace `drop` so nothing is posted.

### `harness.py` — the simulator callback

```python
from geouibench.harness import ConversationRunner, conversation_record

runner = ConversationRunner(app, "protocol", run_dir=run_dir, cdp_endpoint=None, dataset="gold", run_name="r1")
runner.start_golden("core-1")
turn = await runner.respond("render A", [], "conv-1")   # pass runner.respond (a bound async method) as deepeval's model_callback
```

Each call builds the agent on first use, resets the shared browser tab on a new
conversation, runs the turn traced, appends to `turns.jsonl` / `errors.jsonl`,
saves `traces/<conversation>/<n>.json` and returns a deepeval `Turn` whose metadata
carries the trace, the final URL and the usage. `conversation_record(test_case, ...)`
turns a scored `ConversationalTestCase` into the `ConversationRecord` row of
`conversations.jsonl` (traces by path, not inline).

### `metrics.py` — the six metrics and the stopping rule

```python
from geouibench.metrics import metrics_for, gold_metrics, synthetic_metrics, deterministic_only, state_reached_controller, judge_model

metrics = metrics_for(app, meta, judge_model())      # all six for gold goldens, five (no Success) without an expected state
deterministic_only(metrics)                          # Success, Tool / Time / Token efficiency: no LLM, same offline and live
controller = state_reached_controller(app)           # ConversationSimulator(stopping_controller=...): stop once expected_state + checkpoints are reached, or at the golden's cap
```

Classes: `SuccessMetric(app)`, `CompletionMetric(app, model)`, `ToolEfficiencyMetric(app)`,
`TimeEfficiencyMetric()`, `TokenEfficiencyMetric()`, `turn_relevancy_metric(model)`.
Thresholds and `JUDGE_MODEL_NAME` (`gpt-5.2`) are module constants.

### `runner.py` — one golden, one agent kind

```python
from geouibench.runner import run_golden, ensure_run_info

ensure_run_info(app_dir, run_dir, run_name="r1", datasets=app_dir.select_datasets("gold"))   # run.json, written once
record = run_golden(runner, golden, dataset_name="gold", judge=judge_model(), smoke=False)   # simulate → assert_test → append to conversations.jsonl
```

A simulator failure is recorded (`metadata.simulator_error`) and re-raised; a
threshold failure is recorded with its scores and re-raised by deepeval.
`simulator_factory`, `metrics` and `evaluate` are injectable for offline tests.

### `evals/test_benchmark.py` — the one deepeval suite

Not collected by plain `pytest` (outside `testpaths`, and it skips itself without
`BENCHMARK_APP` and `BENCHMARK_RUN`). The CLI runs it; by hand:

```bash
BENCHMARK_APP=benchmarks/<app> BENCHMARK_AGENT=<kind> BENCHMARK_DATASET=gold BENCHMARK_RUN=<run-id> \
DEEPEVAL_RESULTS_FOLDER=benchmarks/<app>/results/<run-id>/deepeval \
uv run deepeval test run benchmarks/geouibench/evals/test_benchmark.py -k core-4 --identifier <run-id>-<kind>
```

### `synthetic.py` — goldens from goldens

```python
from geouibench import SyntheticStyle
from geouibench.synthetic import generate, contexts_from_goldens, prepare

style = SyntheticStyle(scenario_context="...", conversational_task="...", participant_roles="...",
                       scenario_format="...", expected_outcome_format="...", persona="...",
                       max_user_simulations=4, max_goldens_per_context=2)
generate(style, gold_path=app_dir.dataset("gold"), out_path=app_dir.datasets_dir / "synthetic_queries.json", model="gpt-5.2")
```

Put the `SyntheticStyle` in the app's `app.py` as `SYNTHETIC_STYLE` and the CLI's
`synthetic` command does this.

### `score.py`, `summary.py`, `summarize.py`, `run_dir.py` — after a run

```python
from geouibench.score import score_run
from geouibench.summarize import summarize_run
from geouibench.run_dir import read_run_info, load_conversations, load_turns, load_errors

score_run(run_dir)                                   # deterministic four from the committed traces; keys=("success","tool",...) or model_name for the LLM ones
summary = summarize_run(run_dir)                     # Summary(rows, ratios, totals); also writes summary.json / summary.md
load_conversations(run_dir); load_turns(run_dir); load_errors(run_dir)   # typed rows for your own analysis
```

`summary.py` is pure: `summarize(conversations, turns, reference_agent=...)` and
`render_markdown(summary)` work on records already in memory. Ratios are
`<kind>/<reference>` per golden over tool calls, seconds, cache-adjusted and total
tokens.

### `records.py`, `deepeval_results.py` — rows and scores

`TurnRecord`, `ErrorRecord`, `TurnUsage` (with `cache_adjusted_tokens`),
`append_record` / `load_records` for JSONL, `scrub_paths` for machine-specific paths.
`deepeval_results.entries_from_current_test_run(name)` reads the scores deepeval
recorded for a test case (it scores copies of the metric objects, so the instances
you passed stay blank); `metric_entry(metric)` is the fallback for metrics measured
directly.

## Tests

```bash
uv run pytest -q benchmarks/geouibench/tests     # offline: TestModel agents, a stand-in simulator, no keys
```

`tests/_fake_app.py` is a complete `BenchmarkApp` on `fake://` URLs; copy it to
start a new binding's tests.
