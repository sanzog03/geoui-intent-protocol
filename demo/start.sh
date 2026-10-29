#!/usr/bin/env bash
# Launch a long-lived Chromium with remote-debugging enabled, then run
# a Worldview chat notebook (GeoUI treatment or VLM baseline) against it. The Playwright MCP
# attaches to this Chromium per turn via CDP, so the map's URL / pan /
# zoom / layer state survives across chat turns even though the MCP
# itself doesn't.
#
# Browser: Playwright's bundled Chromium (from
# ~/Library/Caches/ms-playwright/...) is used by default. It gets
# auto-installed via `npx playwright install chromium` on first run
# (~150 MB, one-time). To use a different browser instead, set
# CHROME_BIN to its executable.
#
# Re-running the script reattaches to the same Chromium instead of
# spawning a second one. Kill the browser manually when you're done:
#
#     pkill -f "remote-debugging-port=9222"
#
# Overrides via env vars:
#   CHROME_BIN                  path to a Chrome/Chromium binary
#                               (skips Playwright auto-resolve)
#   PLAYWRIGHT_BROWSERS_PATH    Playwright cache root (default
#                               ~/Library/Caches/ms-playwright)
#   CDP_PORT                    remote-debugging port (default 9222)
#   WORLDVIEW_CHROMIUM_PROFILE  user-data-dir (default /tmp/worldview-chromium)
#   MARIMO_MODE                 "run" (default) or "edit"
#   AGENT                       "geoui" (default), "vlm" or "maplibre" — which agent
#   GEOUI_APP_URL               maplibre only: where `npm run dev -w demo/maplibre`
#                               serves the app (default http://127.0.0.1:5173)
#                               demo/chat.py runs (treatment vs baseline)
#
# Platform support:
#   - Bash + POSIX userspace (curl, ls, npx, uv). Does NOT run natively
#     on Windows cmd/PowerShell.
#   - Tested on macOS (Apple Silicon).
#   - Linux: the launch / CDP / marimo plumbing is portable, but the
#     Playwright Chromium auto-resolver below currently globs the
#     macOS-specific cache layout
#     (chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium).
#     On Linux you'll need to either:
#       (a) extend `find_playwright_chromium` to also match
#           chromium-*/chrome-linux/chrome under ~/.cache/ms-playwright, or
#       (b) set CHROME_BIN explicitly to a Chromium / Chrome binary.
#   - Windows: not supported natively. Workaround via WSL:
#       1. Install WSL (PowerShell, admin):  wsl --install
#       2. From the WSL shell, clone the repo and run start.sh from
#          inside WSL - it executes as Linux, so the Linux notes
#          above apply (cache at ~/.cache/ms-playwright, binary at
#          chrome-linux/chrome; either extend the resolver or set
#          CHROME_BIN). `npx playwright install chromium` inside WSL
#          will fetch the Linux Chromium build.
#       3. Open http://localhost:<marimo-port> in your Windows browser
#          - WSL2 forwards localhost transparently.

set -euo pipefail

MARIMO_MODE="${MARIMO_MODE:-run}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Chromium launch / reattach lives in demo/chromium.sh (shared with the
# benchmark runner); it exports PLAYWRIGHT_CDP_ENDPOINT.
# shellcheck source=./chromium.sh
source "$SCRIPT_DIR/chromium.sh"
ensure_chromium || exit 1

# Run marimo from the repo root (one level up from this script) so the
# benchmark logger writes to <repo>/benchmarks/worldview_legacy/ and `uv run` picks up the
# project environment.
cd "$SCRIPT_DIR/.."
AGENT="${AGENT:-geoui}"
case "$AGENT" in geoui|vlm|maplibre) ;; *) echo "AGENT must be 'geoui', 'vlm' or 'maplibre' (got '$AGENT')" >&2; exit 2 ;; esac
export AGENT   # demo/chat.py reads it to pick the agent

if [[ "$AGENT" == "maplibre" ]]; then
    # The MapLibre demo has no plugin and no remote MCPs; it needs the Vite dev
    # server (npm run dev -w demo/maplibre) so the agent has a page to drive.
    export GEOUI_APP_URL="${GEOUI_APP_URL:-http://127.0.0.1:5173}"
    if ! curl -fs -o /dev/null "$GEOUI_APP_URL"; then
        echo "Error: the MapLibre demo is not answering at $GEOUI_APP_URL. Start it first: npm run dev -w demo/maplibre" >&2
        exit 2
    fi
    echo "MapLibre demo at $GEOUI_APP_URL"
else
    if [[ -z "${WORLDVIEW_PLUGIN_DIR:-}" && ! -f demo/worldview/agents/artifact/worldview/geoui/akd-plugins/plugins/worldview-assistant/.mcp.json ]]; then
        echo "Error: the worldview-assistant plugin is missing. Run: git submodule update --init" >&2
        exit 2
    fi
    # Pre-warm remote MCP endpoints (auto-discovered from the agent's
    # capability list) so the first chat turn doesn't pay cold-start
    # latency. `|| true` keeps a failed warm from aborting launch — the
    # agent will retry on its first real call.
    uv run python -m worldview.agents.warm_mcps || true
fi
echo

exec uv run marimo "$MARIMO_MODE" demo/chat.py
