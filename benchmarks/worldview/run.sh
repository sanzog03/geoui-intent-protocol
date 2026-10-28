#!/usr/bin/env bash
# Run the deepeval benchmark: both Worldview agents on the same goldens.
#
#     ./benchmarks/worldview/run.sh [gold|synthetic|all] [run-id] [agent...]
#
#   dataset  which goldens to simulate (default: gold)
#   run-id   results folder under benchmarks/worldview/results/ (default: <date>-<dataset>)
#   agent    one or more of geoui, vlm (default: both, geoui first)
#
# One `deepeval test run` per agent, sequentially (both agents share one
# Chromium tab, so the suite must never run with -n), then the summary.
# Set BENCHMARK_SMOKE=1 to run only the first gold golden with one extra
# user turn per agent, as a quick end-to-end check.
#
# Needs: .env with OPENAI_API_KEY and the plugin's MCP keys (see
# .env.example), the akd-plugins submodule, Node (npx) for the Playwright
# MCP and Chromium, and `uv sync` done once.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$REPO_DIR"

DATASET="${1:-gold}"
RUN="${2:-$(date +%Y-%m-%d)-${DATASET}}"
shift $(( $# > 2 ? 2 : $# ))
AGENTS=("$@")
if [[ ${#AGENTS[@]} -eq 0 ]]; then
    AGENTS=(geoui vlm)
fi
case "$DATASET" in gold|synthetic|all) ;; *) echo "dataset must be gold, synthetic or all (got '$DATASET')" >&2; exit 2 ;; esac
for a in "${AGENTS[@]}"; do
    case "$a" in geoui|vlm) ;; *) echo "agent must be geoui or vlm (got '$a')" >&2; exit 2 ;; esac
done

if [[ -z "${WORLDVIEW_PLUGIN_DIR:-}" && ! -f demo/worldview/agents/artifact/worldview/geoui/akd-plugins/plugins/worldview-assistant/.mcp.json ]]; then
    echo "Error: the worldview-assistant plugin is missing. Run: git submodule update --init" >&2
    exit 2
fi
if [[ "$DATASET" != "gold" && ! -f benchmarks/worldview/datasets/synthetic_queries.json ]]; then
    echo "Error: benchmarks/worldview/datasets/synthetic_queries.json is missing; see benchmarks/worldview/README.md" >&2
    exit 2
fi

# shellcheck source=../../demo/chromium.sh
source demo/chromium.sh
ensure_chromium || exit 1

export DEEPEVAL_TELEMETRY_OPT_OUT=YES
export DEEPEVAL_NO_INSPECT_PROMPT=1
export BENCHMARK_DATASET="$DATASET"
export BENCHMARK_RUN="$RUN"
RUN_DIR="benchmarks/worldview/results/$RUN"
export DEEPEVAL_RESULTS_FOLDER="$RUN_DIR/deepeval"
mkdir -p "$RUN_DIR"

echo "Run: $RUN  dataset: $DATASET  agents: ${AGENTS[*]}  smoke: ${BENCHMARK_SMOKE:-0}"
echo "Results: $RUN_DIR"
echo

# Pre-warm the remote MCP endpoints so the first turn doesn't pay cold-start latency.
uv run python -m worldview.agents.warm_mcps || true
echo

status=0
for AGENT in "${AGENTS[@]}"; do
    echo "=== agent: $AGENT ==="
    if ! BENCHMARK_AGENT="$AGENT" uv run deepeval test run benchmarks/worldview/evals/test_worldview.py \
            --identifier "$RUN-$AGENT" --ignore-errors --display all; then
        echo "deepeval reported failures for $AGENT (metric thresholds); continuing" >&2
        status=1
    fi
    echo
done

uv run python -m geobench.summarize "$RUN_DIR"
echo
echo "Done. Review and commit $RUN_DIR (summary.md, conversations.jsonl, turns.jsonl, traces/, deepeval/)."
exit $status
