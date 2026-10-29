# geouibench — a mechanism-neutral benchmark harness for geospatial-UI agents

`geouibench` benchmarks agents that drive a geospatial user interface, whatever the
mechanism: an agent that speaks the GeoUI protocol and one that clicks through the
UI are treated the same way, as a black box that takes user text and leaves the
application in some state. It knows pydantic-ai (to run the agent), deepeval (to
simulate the user and score the conversation) and the `GeoIntent` schema (only as
the vocabulary for "what is on screen"). It knows nothing about any particular
application; an application plugs in through `BenchmarkApp`.

The Worldview bindings in `../worldview/` are the first user and the worked example.

## How a run works

```
dataset JSON ──goldens_for(agent)──▶ ConversationalGolden (+ verbatim opener)
                                         │
                       deepeval ConversationSimulator (simulated user, gpt-5.2)
                                         │  calls, per user turn
                     ConversationRunner(app, kind).respond     ← harness.py
                                         │  traced_turn: agent.run under a deepeval span
                           TurnTrace (llm/tool spans)  +  TurnRecord row
                                         │
                    assistant Turn{content, tools_called, metadata{trace, final_url, …}}
                                         │  until state_reached_controller says stop
                         ConversationalTestCase ──assert_test──▶ the six metrics
```

Everything a turn produced is written under `results/<run>/` (`turns.jsonl`,
`errors.jsonl`, `traces/<conversation>/<turn>.json`, `conversations.jsonl`), so
`python -m geouibench.score <run>` can recompute the deterministic metrics later
without an agent or a browser, and `python -m geouibench.summarize <run>` writes
`summary.json` / `summary.md` with the cross-agent ratios.

## The app seam (`geouibench.app.BenchmarkApp`)

```python
class BenchmarkApp(Protocol):
    name: str                                   # "worldview"
    agent_kinds: tuple[str, ...]                # ("geoui", "vlm") — the variants under comparison
    auto_layers: frozenset[str]                 # layers the app injects by itself; ignored unless expected
    discovery_tools: frozenset[str]             # tool names that count as waste on fully specified prompts
    def build_agent(self, kind, *, cdp_endpoint, extra_capabilities) -> Agent   # harness passes tracing here
    def chatbot_role(self, kind) -> str         # for deepeval's conversational metrics
    def output_url(self, output) -> str | None  # structured output → the app URL; None for a text turn
    def observe(self, url) -> UIState           # what the app shows at that URL (hidden layers dropped)
```

`observe` is the only place an application's URL grammar is parsed. Both of
Worldview's agents end a turn with a Worldview URL (one from its render tool, one
read back from `window.location.href`), and `observe` turns either into the same
`UIState`, so the judge never knows which mechanism produced it.

## Dataset format (`geouibench.datasets`)

A dataset is a plain JSON list of deepeval `ConversationalGolden` objects
(`name`, `scenario`, `expected_outcome`, `persona`), so deepeval's loaders and
`deepeval generate --method goldens` read it unchanged. The harness's additions
live in `additional_metadata`:

| key | meaning |
|---|---|
| `openers` | `{agent_kind: text}`: the verbatim first user turn per agent. Injected as the golden's opening `Turn`; the simulator improvises the rest from `scenario`. |
| `expected_state` | `ExpectedState`: layers (id → opacity or `null`), `time`, `crs`, `compare`, `chart`, `styling`. Absent on synthetic goldens. |
| `checkpoints` | partial `ExpectedState`s that must each be reached by some assistant turn (multi-turn workflows). |
| `max_user_simulations` | extra user turns after the opener (0 = single-shot; the stopping rule enforces it). |
| `state_threshold` | pass threshold of the Success metric (1.0 single-shot, 0.8 workflows). |
| `fully_specified` | the prompt says discovery is done; discovery tool calls count as waste. |
| `budgets` | `{seconds_per_turn, tokens_per_turn}`; dataset-level defaults are passed by the binding. |

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
- deepeval cannot build a multi-turn test case from traces locally (that is a Confident AI
  feature), so the conversation comes from the simulator and the per-turn traces are
  stitched onto its `Turn`s.

## Binding another application

Implement `BenchmarkApp`, write a dataset with `openers` for your agent kinds and
`expected_state` in the `GeoIntent` vocabulary, and copy `../worldview/evals/test_worldview.py`
and `run.sh`. Run with `deepeval test run`, one agent kind per invocation, never `-n`
if your agents share a browser.

## Development

```bash
uv run pytest -q benchmarks/harness/geouibench/tests     # offline; no keys, no browser, no network
```

The unit tests drive a pydantic-ai `TestModel` agent through the real runner and the
real deepeval instrumentation, so the trace capture, the record files and the offline
re-score are exercised end to end without an LLM.
