# MapLibre benchmark — the GeoUI agent on an application with no URL state

The second app directory for `geouibench`: the same six metrics and the same gold scenarios as
[`../worldview`](../worldview) (minus the chart ones, which the demo does not attach), run against
the [MapLibre demo](../../demo/maplibre) through its GeoUI MCP over CDP (the `maplibre` package in the same directory).

- **geoui** — `maplibre.agents.build_maplibre_agent`: a bare pydantic-ai agent with only the three
  GeoUI tools. No skill, no discovery MCPs, no browser tools; the page's catalogue
  (`geo_ui_list_intent_extensions_tool`) is all it knows about the application.

What differs from Worldview is how the state is read back. The agent reports no URL; after every turn
`MaplibreApp.snapshot()` reads `window.geoui.getState()` from the live page and stores the GeoIntent
itself as the turn's handle (`geoui+json:<json>`), which `observe()` parses at scoring time, so
`geouibench score` reruns offline exactly as for Worldview.

## Layout

```
benchmarks/maplibre/
├── app.py                      MaplibreApp (APP): prepare() (Chromium + demo reachable), build_agent, snapshot(), observe()
├── datasets/gold_dataset.json  Core 1–4, 6 and workflows A/B derived from ../worldview, geoui opener only, no chart
├── tests/                      offline tests (binding, dataset validity, catalogue coverage)
└── results/<run-id>/           one folder per run, committed (same files as ../worldview)
```

## Running

```bash
npm run dev &                      # the app at http://127.0.0.1:5173 (GEOUI_APP_URL to override)
uv run python -m geouibench run benchmarks/maplibre gold --smoke --run-id smoke   # one golden, quick
uv run python -m geouibench run benchmarks/maplibre gold --run-id 2026-10-29-gold
uv run python -m geouibench summarize benchmarks/maplibre 2026-10-29-gold
```

`prepare()` launches or reuses Chromium on CDP (`demo/chromium.sh`) and fails early with the `npm run dev`
hint when the demo is not answering. `OPENAI_API_KEY` in `.env` is needed for the agent and the judge.

## Comparing with Worldview

Same goldens, same metrics, same budgets: the per-golden Success / Completion / efficiency numbers in
`summary.md` are directly comparable with the Worldview geoui agent's. Expect fewer tool calls (no discovery
servers, no browser navigation: list, optional get_state, render) and no "undeclared extension" retries (the
page tells the agent what it supports).
