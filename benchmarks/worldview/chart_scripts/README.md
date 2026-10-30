# chart_scripts — slide charts from a benchmark run

Each script reads one run's `csv/conversations.csv` (written by
`python -m geouibench export`) and writes a PNG, an SVG and a CSV of the exact
numbers it plotted to `<run>/charts/`. Nothing is recomputed: every bar is a
mean, a count or a rate of a column in that file, so a chart can be checked
against its CSV and the CSV against `conversations.csv`.

They are standalone [uv scripts](https://docs.astral.sh/uv/guides/scripts/): matplotlib is declared
inline, so the project's lockfile is untouched.

```bash
uv run benchmarks/worldview/chart_scripts/make_all.py                       # every chart, newest run
uv run benchmarks/worldview/chart_scripts/cost_per_task.py --set gold        # one chart, one variant
uv run benchmarks/worldview/chart_scripts/cost_per_task.py --run benchmarks/worldview/results/<run-id>
```

| script | chart | main columns |
|---|---|---|
| `cost_per_task.py` | mean input / output / total / reasoning / cache-read tokens, LLM requests and tool calls per task, log scale, with three VLM ÷ GeoUI headline tiles | `input_tokens`, `output_tokens`, `total_tokens`, `reasoning_tokens`, `cache_read_tokens`, `llm_requests`, `tool_calls` |
| `time_per_task.py` | mean agent seconds per task for gold, synthetic and all queries; split into model, tool and other time | `seconds`, `llm_seconds`, `tool_seconds` |
| `correctness.py` | share of tasks correct per query set, and the pass rate of each of the six metrics, labelled `k/n` | `correct`, `*_pass` |
| `per_query.py --measure M` | one measure per query, side by side, sorted by VLM ÷ GeoUI, wrong answers marked | `tool_calls`, `seconds`, `cache_adjusted_tokens`, `total_tokens`, `llm_requests`, `cost_usd` |
| `make_all.py` | runs the variants above | |
| `common.py` | loading, filtering, colours, bar and tile helpers | |

## What a bar averages over

The filters live in `common.select` and every script prints what they removed:

1. `--set all|gold|synthetic` picks the query set (default `all`).
2. Conversations with a `simulator_error` are dropped. The simulated user failed before
   the agent ran, so the row has zero turns and would otherwise read as a free task.
3. **Paired by default.** Only queries with a row for both agents are kept, so both
   bars average over the same tasks. `--unpaired` averages each agent over everything
   it completed.
4. `--correct-only` keeps only conversations the agent got right. Paired, that means
   queries both agents got right, which answers "what does a correct answer cost".

`correct` is the Success pass on gold queries (the final map matches the expected
layers, date and view) and the Completion pass on synthetic ones (gpt-5.2 judges the
user's goal met), as `correctness_basis` records.

## Reading the numbers

- A task is one conversation: a five-turn workflow counts once, so its tokens are
  the sum of its turns.
- Ratios are VLM mean ÷ GeoUI mean, not the mean of per-query ratios.
- `cost_usd` is low on conversations where an errored turn left no price
  (`cost_complete` = False in `conversations.csv`); the token columns are complete.
- Colours: GeoUI `#3F7FB0` with a cross-hatch, VLM `#E39B2F` with dots, checked with the
  dataviz palette validator for colour-blind separation. The orange is low contrast on
  white, so every bar carries its value and a hatch.
