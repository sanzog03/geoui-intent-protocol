# benchmarks/ — `geouibench` and the apps that run on it

```
benchmarks/
├── pyproject.toml     the one benchmark workspace member: `geouibench` (owns deepeval)
├── geouibench/        the utility: no application named anywhere inside it (API reference in its README)
├── worldview_legacy/  the earlier Worldview notebook-driven procedure and the frozen poster logs
└── worldview/         the first app directory: NASA Worldview, GeoUI agent vs VLM baseline
```

`geouibench` benchmarks agents that drive a geospatial user interface, whatever
the mechanism: an agent that speaks the GeoUI protocol and one that clicks through
the UI are treated the same way, as a black box that takes user text and leaves the
application in some state. It knows pydantic-ai (to run the agent), deepeval (to
simulate the user, generate synthetic goldens and score the conversation) and the
`GeoIntent` schema (only as the vocabulary for "what is on screen"). An application
plugs in through an **app directory**; the utility never imports it by name.

## Benchmark a new demo in four steps

1. **Make an app directory** `benchmarks/<name>/` with an `app.py` that defines a
   module-level `APP` satisfying `geouibench.BenchmarkApp` (below). Optionally give
   the class a `prepare()` hook (launch a browser, warm services; return environment
   variables for the benchmark processes) and the module a `SYNTHETIC_STYLE`.
2. **Write a gold dataset** `benchmarks/<name>/datasets/gold_dataset.json`: a JSON
   list of deepeval conversational goldens with `openers` per agent kind and an
   `expected_state` in the `GeoIntent` vocabulary (format below).
3. **Run it**, then look at `results/<run-id>/summary.md`:

   ```bash
   uv run python -m geouibench run benchmarks/<name> gold --smoke --run-id smoke   # one golden, every agent kind
   uv run python -m geouibench run benchmarks/<name> gold --run-id 2026-10-28-gold
   ```

4. **Expand with synthetic goldens** and rerun on both sets:

   ```bash
   uv run python -m geouibench synthetic benchmarks/<name>      # gold → deepeval generate → datasets/synthetic_queries.json
   uv run python -m geouibench run benchmarks/<name> all --run-id 2026-10-29-all
   ```

`benchmarks/worldview/` is the worked example: one `app.py`, two datasets, committed
runs, and a few tests of its own.

## The CLI (`python -m geouibench`)

| command | does |
|---|---|
| `run <app dir> <dataset>... [--run-id ID] [--agent KIND ...] [--smoke]` | calls the app's `prepare()`, writes `run.json`, runs `deepeval test run` on the generic eval file once per agent kind (sequentially: agents of one app may share a browser), writes the summary |
| `score <run dir> [--metrics all\|success,tool,...] [--model]` | recomputes metrics from the committed traces and transcripts; the deterministic four need no network |
| `summarize <run dir> [--reference KIND]` | rewrites `summary.json` / `summary.md` and scrubs absolute paths |
| `synthetic <app dir> [--gold NAME] [--out NAME] [--model]` | gold → contexts → `deepeval generate --method contexts` with the app's `SYNTHETIC_STYLE` → prepared dataset |
| `datasets <app dir>` | lists the datasets the directory holds |

Dataset names resolve to `datasets/<name>.json` or the one file whose stem starts
with the name (`gold` → `gold_dataset.json`, `synthetic` → `synthetic_queries.json`);
`all` means every dataset in the directory.

## How a run works

```
<app dir>/datasets/*.json ──goldens_for(agent kind)──▶ ConversationalGolden (+ verbatim opener)
                                         │
                       deepeval ConversationSimulator (simulated user, gpt-5.2)
                                         │  calls, per user turn
                     ConversationRunner(app, kind).respond          ← harness.py
                                         │  traced_turn: agent.run under a deepeval span
                           TurnTrace (llm/tool spans)  +  TurnRecord row
                                         │
                    assistant Turn{content, tools_called, metadata{trace, final_url, …}}
                                         │  until state_reached_controller says stop
                         ConversationalTestCase ──assert_test──▶ the six metrics   ← runner.run_golden
```

Everything a turn produced is written under `<app dir>/results/<run-id>/`
(`run.json`, `turns.jsonl`, `errors.jsonl`, `traces/<conversation>/<turn>.json`,
`conversations.jsonl`, deepeval's own result file, `summary.json` / `summary.md`),
so `score` can recompute the deterministic metrics later without an agent or a
browser, and the folder can be committed as the evidence behind a number.

## The app seam (`geouibench.app.BenchmarkApp`)

```python
class BenchmarkApp(Protocol):
    name: str                                   # "worldview"
    agent_kinds: tuple[str, ...]                # ("geoui", "vlm") — the first is the reference for ratios
    auto_layers: frozenset[str]                 # layers the app injects by itself; ignored unless expected
    discovery_tools: frozenset[str]             # tool names that count as waste on fully specified prompts
    budgets: Budgets                            # seconds and cache-adjusted tokens per turn, same for every kind
    def build_agent(self, kind, *, cdp_endpoint, extra_capabilities) -> Agent   # the utility passes tracing here
    def chatbot_role(self, kind) -> str         # for deepeval's conversational metrics
    def output_url(self, output) -> str | None  # the app URL in a turn's output; None for a text-only turn
    def observe(self, url) -> UIState           # what the app shows at that URL (hidden layers dropped)
    # optional: def prepare(self) -> Mapping[str, str]
```

`observe` is the only place an application's URL grammar is parsed. Every agent
kind must end a turn with an application URL (from a render tool, or read back from
the browser); `observe` turns any of them into the same `UIState`, so the judge
never knows which mechanism produced it.

## Dataset format (`geouibench.datasets`)

A dataset is a plain JSON list of deepeval `ConversationalGolden` objects
(`name`, `scenario`, `expected_outcome`, `persona`), so deepeval's loaders and
`deepeval generate --method goldens` read it unchanged. The utility's additions
live in `additional_metadata`:

| key | meaning |
|---|---|
| `openers` | `{agent_kind: text}`: the verbatim first user turn per agent. Injected as the golden's opening `Turn`; the simulator improvises the rest from `scenario`. |
| `expected_state` | `ExpectedState`: layers (id → opacity or `null`), `time`, `crs`, `compare`, `chart`, `styling`. Absent on synthetic goldens. |
| `checkpoints` | partial `ExpectedState`s that must each be reached by some assistant turn (multi-turn workflows). |
| `max_user_simulations` | extra user turns after the opener (0 = single-shot; the stopping rule enforces it). |
| `state_threshold` | pass threshold of the Success metric (1.0 single-shot, 0.8 workflows). |
| `fully_specified` | the prompt says discovery is done; discovery tool calls count as waste. |
| `budgets` | `{seconds_per_turn, tokens_per_turn}`; the app's `budgets` fill in when absent. |

`validate_dataset(path, agent_kinds=...)` checks all of it; `dataset_hash(path)`
goes into `run.json` so a rerun can prove it used the same goldens.

## Metrics (`geouibench.metrics`)

| # | metric | kind | score | pass |
|---|---|---|---|---|
| 1 | **Success** | deterministic | final URL state vs `expected_state`: matched / expected fields | ≥ `state_threshold` |
| 2 | **Completion** | checkpoints + LLM | fraction of checkpoints reached, averaged with deepeval `ConversationCompletenessMetric` | ≥ 0.7 |
| 3 | **Tool efficiency** | deterministic | 1 − wasted / total tool calls (repeats, errored calls, discovery on fully specified prompts, error turns) | ≥ 0.7 |
| 4 | **Time efficiency** | deterministic | min(1, budget / mean seconds per assistant turn) | ≥ 0.5 |
| 5 | **Token efficiency** | deterministic | min(1, budget / mean cache-adjusted tokens per turn); tokens = input − cache_read + 0.1·cache_read + output | ≥ 0.5 |
| 6 | **Turn relevancy** | LLM | deepeval `TurnRelevancyMetric` | ≥ 0.7 |

The deterministic four read `TurnTrace` from each assistant turn's metadata, never a
live object, so a live run and an offline re-score compute the same numbers. The LLM
judge is `OpenAIModel("gpt-5.2")`, pinned in `JUDGE_MODEL_NAME`. Budgets are a fixed
yardstick identical for every agent kind; the cross-agent comparison is the summary's
ratios, not pass/fail.

## How traces are captured (`geouibench.tracing`)

The agent is instrumented with deepeval's pydantic-ai integration
(`Instrumentation(settings=DeepEvalInstrumentationSettings())`), passed through the
application's `build_agent(extra_capabilities=...)` — no agent code changes. Each
turn runs under a deepeval `@observe` span, which routes pydantic-ai's OpenTelemetry
spans to deepeval's in-process trace manager; the finished trace is read back from
`current_trace_context` before the span closes and marked `drop` so nothing is posted.

Established by a spike on 2026-10-28 (deepeval 4.3.2, pydantic-ai 2.63):

- LLM spans carry input/output token counts per request; their sum equals pydantic-ai's
  `result.usage`. Cache-read and reasoning tokens are **not** on the spans and are taken
  from `result.usage` (`TurnTrace.usage`, `usage_source="pydantic_ai"`).
- Tool spans carry arguments and results (results truncated to 2000 chars when saved).
- MCP `tools/list` calls appear as untyped spans (listed under `other_spans`), and MCP
  tool calls appear twice (an outer typed span with args/result and an inner duplicate
  with no input); the mapping keeps the outer one.
- deepeval's `Observer` never clears `current_trace_context`, so `traced_turn` clears
  it around every turn; otherwise each later turn's trace would accumulate the earlier
  spans.
- deepeval cannot build a multi-turn test case from traces locally (that is a Confident AI
  feature), so the conversation comes from the simulator and the per-turn traces are
  stitched onto its `Turn`s.

## Running by hand

The CLI is a thin wrapper; the eval file runs on its own too, one agent kind per
invocation (never `-n` when the kinds share a browser):

```bash
BENCHMARK_APP=benchmarks/<name> BENCHMARK_AGENT=<kind> BENCHMARK_DATASET=gold BENCHMARK_RUN=<run-id> \
DEEPEVAL_RESULTS_FOLDER=benchmarks/<name>/results/<run-id>/deepeval \
uv run deepeval test run benchmarks/geouibench/evals/test_benchmark.py -k core-4 --identifier <run-id>-<kind>
```

`-k <golden name>` selects one scenario. Plain `pytest` on the eval file writes no
deepeval result JSON and, without `BENCHMARK_APP` and `BENCHMARK_RUN`, skips itself.

## Development

```bash
uv run pytest -q benchmarks/geouibench/tests     # offline; no keys, no browser, no network
```

The unit tests drive a pydantic-ai `TestModel` agent through the real runner, the
real deepeval instrumentation and the run loop (with a stand-in simulator), so the
trace capture, the record files, the CLI and the offline re-score are exercised end
to end without an LLM.
