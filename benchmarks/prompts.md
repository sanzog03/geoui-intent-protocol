# Benchmark prompt suite — GeoUI vs VLM-baseline

A small, hand-curated set of conversation scripts covering the
distinct *kinds* of interaction a Worldview user would actually do.
Each script is a sequence of user turns; run the same script on
both agents (with their logs reset between agents) and compare the
JSONL rows written to `benchmarks/runs.jsonl`.

The suite is split into a **Core 6** (run these for the poster
panel) and an **Optional 4** (extra coverage / edge cases — run
if there's time).

## Isolating the interaction mechanism

The empirical claim of the poster is about the **cost of applying
an intent** — `geoui_render_intent` → `browser_navigate` vs
Playwright UI driving. To measure that without the *discovery
loop* (CMR / vector-DB lookups + a mandatory confirmation
round-trip) dominating every turn, each Core prompt is written to
fire the agent's **Step 3.5: Fully-specified intent fast-path**.

Two ingredients make a prompt fully-specified:

1. **Per-agent layer naming**, matching what each agent
   downstream consumes:
   - **GeoUI agent** → exact Worldview registry layer ID, e.g.
     ``MODIS_Aqua_Aerosol_Optical_Depth_3km``. Distinguishable by
     underscores + exact capitalisation.
   - **VLM agent** → verbose searchable layer name as it appears
     in Worldview's "Add Layers" search bar, e.g.
     `"MODIS Aqua Aerosol Optical Depth"`. Human-readable.
2. **An explicit signal** that you've already done discovery
   off-band — phrasings like "I've already identified this exact
   layer ID" or "no further dataset discovery or confirmation
   needed". This is what trips Step 3.5 over Step 4 in the
   system prompt.

Date is the same on both agents (`YYYY-MM-DD`). Location is a
readable **place name** (e.g. "Gulf of Mexico", "Florida",
"contiguous US"); each agent translates the name appropriately —
GeoUI infers a bbox for `viewport.bbox`, VLM drives Worldview's
location-search UI.

That asymmetry is intentional: it lets each agent receive the
shape of input it can *consume directly*, so the comparison is
about the *output* mechanism, not the input format.

## How to run

1. `./demo/start.sh` or `AGENT=vlm ./demo/start.sh` — open
   the notebook.
2. Click **Reset conversation memory** so the new session gets a
   fresh `log_session_id`.
3. Paste each user turn from a script below, wait for the agent
   to finish, then paste the next turn. **Use the prompt that
   matches the agent you're running** (GeoUI variant or VLM
   variant).
4. When done, switch agents (you can keep the same Chromium up;
   just open the other notebook on a different marimo port or in
   sequence) and repeat the same script with the other variant.
5. Run an analysis script over `benchmarks/runs.jsonl` to
   compare.

## Goals of the suite

- **Cover the interaction *types*, not arbitrary scenarios.** Each
  script tests a distinct capability: initial render, refining
  (date/pan), extensions (compare, chart), list complexity.
- **Keep prompts in verbose natural-language form**, not as
  imperative commands. The structured fields appear *inside* a
  natural sentence that also signals off-band confirmation.
- **Hold the discovery / dataset selection the same across
  agents.** Both notebooks have identical CMR + IESO + SDE tools;
  the comparison should be about *observation + action*, not
  about who finds the dataset faster — which is exactly what
  Step 3.5 enforces when the prompts trip the fast-path.

---

# Core 6 (run these)

The minimum set that tells the poster's story. Each one adds a
distinct dimension: baseline → temporal refinement → spatial
refinement → extensions → list-complexity scaling. No two repeat
the same kind of difference.

## 1. Single-shot initial render (baseline)

The simplest workflow: open Worldview, enable one layer, set the
date. One turn, no refinement.

**GeoUI:**
```
I want to visualize the layer `MODIS_Aqua_Aerosol_Optical_Depth_3km` on Worldview for 2025-09-15, focused on the contiguous US. I've already identified this exact layer ID — please render it directly without further dataset discovery or asking me to confirm.
```

**VLM:**
```
I want to visualize the "MODIS Aqua Aerosol Optical Depth 3km" layer on NASA Worldview for 2025-09-15, focused on the contiguous US. I've already picked this layer — please add it via Worldview's Add Layers search and set up the view directly, no further dataset discovery or confirmation needed.
```

**Role in suite:** the floor. Denominator for every other ratio.

---

## 2. Refining — change date only

Same layers and viewport; just shift time. The cheapest possible
refinement. *Temporal* axis of refinement.

**GeoUI turn 1:**
```
I want to visualize the layer `VIIRS_SNPP_CorrectedReflectance_TrueColor` on Worldview for 2024-09-26, focused on Florida. I've already identified this exact layer ID — please render it directly without further dataset discovery or asking me to confirm.
```

**VLM turn 1:**
```
I want to visualize the "VIIRS SNPP Corrected Reflectance (True Color)" layer on NASA Worldview for 2024-09-26, focused on Florida. I've already picked this layer — please add it via Worldview's Add Layers search and set up the view directly, no further dataset discovery or confirmation needed.
```

**Turn 2 (identical for both agents — refining):**
```
Now move the date forward by one day, to 2024-09-27.
```

**Role in suite:** purest demonstration of the protocol's
"carry state forward, change one field" advantage.

---

## 3. Refining — pan to a place by name

A *visual* operation that doesn't map cleanly to a single map
control. GeoUI updates `viewport.bbox`; VLM must use Worldview's
search or drag the map. *Spatial* axis of refinement.

**GeoUI turn 1:**
```
I want to visualize the layer `GHRSST_L4_MUR_Sea_Surface_Temperature_Anomalies` on Worldview for 2022-08-19 on a global view. I've already identified this exact layer ID — please render it directly without further dataset discovery or asking me to confirm.
```

**VLM turn 1:**
```
I want to visualize the "GHRSST L4 MUR Sea Surface Temperature Anomalies" layer on NASA Worldview for 2022-08-19 on a global view. I've already picked this layer — please add it via Worldview's Add Layers search and set up the view directly, no further dataset discovery or confirmation needed.
```

**Turn 2 (identical for both agents — refining):**
```
Now pan the map to the Gulf of Mexico.
```

**Role in suite:** spatial counterpart to #2; also the workflow
with existing empirical numbers (the MUR SST anchor).

---

## 4. [NA] Comparison mode (A/B swipe)

Engages the `compare` extension. GeoUI declares
`geoui_extensions=["ext/compare/v1.0.0"]` and sets `compare:*`
fields. VLM has to find the Compare button in the top bar, then
configure the B-side layer.

**GeoUI:**
```
I want to compare two layers side-by-side on Worldview for 2025-08-01: `AIRS_L3_Surface_Air_Temperature_Daily_Day_Mean` as the A-side and `AIRS_L3_Surface_Air_Temperature_Daily_Night_Mean` as the B-side, on a global view, using swipe compare mode with the slider at 50%. I've already identified both exact layer IDs — please render this directly without further dataset discovery or asking me to confirm.
```

**VLM:**
```
I want to compare two layers side-by-side on NASA Worldview for 2025-08-01: "AIRS Surface Air Temperature (Day)" as the A-side and "AIRS Surface Air Temperature (Night)" as the B-side, on a global view, using swipe compare mode with the slider at 50%. I've already picked both layers — please enable comparison via Worldview's UI directly, no further dataset discovery or confirmation needed.
```

**Role in suite:** demonstrates the GeoUI extension story —
that the protocol's advantage scales with workflow richness,
not just simple cases.

---

## 5 [NA]. Charting / time series

Engages the `chart` extension. GeoUI sets `chart:layer`,
`chart:area`, `chart:time`. VLM must enable the chart panel and
draw or type an area of interest.

**GeoUI:**
```
I want to visualize the layer `MOD13Q1_NDVI_16Day` on Worldview for 2024-07-15 over the western US, and also enable Worldview's chart panel showing a time series of that same layer over the same area from 2024-04-01 through 2024-10-31, autoloaded. I've already identified this exact layer ID — please render it directly without further dataset discovery or asking me to confirm.
```

**VLM:**
```
I want to visualize the "MOD13Q1 NDVI 16-Day" layer on NASA Worldview for 2024-07-15 over the western US, and also enable Worldview's chart panel showing a time series of that same layer over the same area from 2024-04-01 through 2024-10-31, autoloaded. I've already picked this layer — please render and enable the chart via Worldview's UI directly, no further dataset discovery or confirmation needed.
```

**Role in suite:** second extension example (pairs with #4) —
shows the extension pattern generalises across capabilities,
not just a one-off.

---

## 6. Multi-layer overlay [VLM couldnot complete. openai timeout]

Stack multiple layers with explicit opacity / ordering. GeoUI's
layer list is one declarative array; VLM must add each layer
individually and adjust each opacity slider.

**GeoUI:**
```
I want to visualize three layers stacked together on Worldview for 2024-07-04 on a global view: `MODIS_Aqua_CorrectedReflectance_TrueColor` at full opacity as the base, `Reference_Labels_15m` at 60% opacity, and `Reference_Features_15m` at 80% opacity. I've already identified all three exact layer IDs — please render this directly without further dataset discovery or asking me to confirm.
```

**VLM:**
```
I want to visualize three layers stacked together on NASA Worldview for 2024-07-04 on a global view: "MODIS Aqua Corrected Reflectance (True Color)" at full opacity as the base, "Reference Labels" at 60% opacity, and "Reference Features" at 80% opacity. I've already picked all three layers — please add them via Worldview's Add Layers search and stack them at those opacities directly, no further dataset discovery or confirmation needed.
```

**Role in suite:** list-complexity scaling — the ratio between
GeoUI and VLM *grows* with N layers, not just shifts by a
constant.

---

# Optional / extended suite (4)

Run if there's time. These are not yet rewritten in the paired
verbose / fast-path form — they remain in the older command-style
phrasing for now. Treat them as natural-language for
discovery-loop testing rather than isolated interaction-mechanism
measurement.

## 7. Refining a previous visualization — zoom

Mechanically similar to #3 pan-by-place on the VLM side (both
are spatial UI ops), but with a less-targeted command. Kept as
optional because #3 is more demanding and already anchored
empirically.

```
Show MODIS Aqua True Color over North America on 2024-07-04.
Now zoom into the San Francisco Bay Area.
```

---

## 8. Ambiguity — clarification round-trip

A *control*: tests whether the discovery loop behaves the same
on both sides (it should — the discovery tools are identical).
Surfaces VLM's tendency to ask *more* clarifying questions
because UI failures are expensive.

```
I want to look at fires over California.
```

---

## 9. Polar projection

Forces `crs="EPSG:3413"` (Arctic) or `crs="EPSG:3031"`
(Antarctic). GeoUI changes one field. VLM has to find the
Projection dropdown.

```
Show MODIS Terra Sea Ice over the Arctic on 2025-03-15 in the polar stereographic projection.
```

---

## 10. Recovery from a misclick (VLM stress test)

Only meaningful for the VLM agent. Tests resilience to the kind
of error this baseline is most prone to.

```
Show MODIS Terra Aerosol over India on 2024-04-10.
Wait, I meant Aqua, not Terra.
```

---

## Analysis recipe

After running the Core 6 on both agents the JSONL file holds
roughly `6 scripts × ~2 turns/script × 2 agents ≈ 24 rows`
(more if you also run the Optional 4). A short analysis script
(e.g. `benchmarks/summarize.py`, future work) groups by
`agent` and `user_prompt` and produces:

- Per-prompt token totals (input / output / total).
- Per-prompt tool-call counts.
- Per-prompt wall-clock time.
- Cumulative totals per agent.
- Cache-adjusted "effective" token cost (raw input − cache reads
  + cache reads × 0.1).
- Headline ratios for each interaction type (date, pan, compare,
  chart, multi-layer).

**Verification that the fast-path fired:** Core-prompt rows
should contain only `geoui_render_intent` + `browser_navigate`
(GeoUI) or `browser_*` tools (VLM). They should **not** contain
`search_collections`, `get_collection_metadata`,
`search_worldview_layers`, `validate_temporal_coverage`, or
`sde_search_tool`. If any of those appear, the prompt didn't
trip Step 3.5 — fix the prompt or the system-prompt wording.

That's the dataset behind the poster's central comparison panel.
