#!/usr/bin/env bash
# Chromium-on-CDP helpers shared by demo/start.sh (the chat notebook) and
# the benchmark's WorldviewApp.prepare() (benchmarks/worldview/app.py). Source this file,
# then call `ensure_chromium`; it launches (or reattaches to) a long-lived
# Chromium with remote debugging on $CDP_PORT and exports
# PLAYWRIGHT_CDP_ENDPOINT for the Playwright MCP to attach to.
#
# Browser: Playwright's bundled Chromium (from
# ~/Library/Caches/ms-playwright/...) is used by default. It gets
# auto-installed via `npx playwright install chromium` on first run
# (~150 MB, one-time). To use a different browser instead, set
# CHROME_BIN to its executable.
#
# Kill the browser manually when you're done:
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
#
# Platform support:
#   - Bash + POSIX userspace (curl, ls, npx). Does NOT run natively
#     on Windows cmd/PowerShell.
#   - Tested on macOS (Apple Silicon).
#   - Linux: the launch / CDP plumbing is portable, but the Playwright
#     Chromium auto-resolver below globs the macOS-specific cache layout
#     (chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium).
#     On Linux either extend `find_playwright_chromium` to also match
#     chromium-*/chrome-linux/chrome under ~/.cache/ms-playwright, or
#     set CHROME_BIN explicitly to a Chromium / Chrome binary.
#   - Windows: not supported natively; use WSL (the Linux notes apply).

CDP_PORT="${CDP_PORT:-9222}"
USER_DATA_DIR="${WORLDVIEW_CHROMIUM_PROFILE:-/tmp/worldview-chromium}"
PW_CACHE="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"

is_cdp_up() {
    curl -fs -o /dev/null "http://localhost:${CDP_PORT}/json/version"
}

# Print the newest cached Playwright Chromium binary path on stdout,
# or return non-zero if none is installed.
#
# NOTE: macOS-only layout. Linux Chromium lives at
# chromium-*/chrome-linux/chrome under ~/.cache/ms-playwright; extend
# the glob below to add Linux support, or set CHROME_BIN explicitly.
find_playwright_chromium() {
    local d
    # `ls -td` orders by mtime newest-first; first executable hit wins.
    for d in $(ls -td "$PW_CACHE"/chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium 2>/dev/null); do
        if [[ -x "$d" ]]; then
            echo "$d"
            return 0
        fi
    done
    return 1
}

# Resolve a usable browser binary, installing Playwright Chromium on
# the fly if neither CHROME_BIN nor a cached install is present.
ensure_browser() {
    if [[ -n "${CHROME_BIN:-}" ]]; then
        if [[ -x "$CHROME_BIN" ]]; then
            echo "$CHROME_BIN"
            return 0
        fi
        echo "Error: CHROME_BIN='$CHROME_BIN' is not an executable file" >&2
        return 1
    fi

    local binary
    if binary=$(find_playwright_chromium); then
        echo "$binary"
        return 0
    fi

    echo "Playwright Chromium not found in $PW_CACHE - installing (one-time, ~150 MB)..." >&2
    if ! command -v npx >/dev/null 2>&1; then
        echo "Error: 'npx' is required to install Playwright Chromium and is not on PATH" >&2
        return 1
    fi
    if ! npx -y playwright install chromium >&2; then
        echo "Error: 'npx playwright install chromium' failed" >&2
        return 1
    fi

    if binary=$(find_playwright_chromium); then
        echo "$binary"
        return 0
    fi
    echo "Error: Playwright Chromium still not found after install (looked in $PW_CACHE)" >&2
    return 1
}

# Launch Chromium on $CDP_PORT unless one is already listening, wait for
# the CDP endpoint, and export PLAYWRIGHT_CDP_ENDPOINT. Returns non-zero
# if no browser could be started.
ensure_chromium() {
    if is_cdp_up; then
        echo "Chromium CDP already up on port ${CDP_PORT} - reusing."
    else
        local chrome
        chrome="$(ensure_browser)" || return 1
        echo "Browser: $chrome"

        echo "Launching Chromium on port ${CDP_PORT}..."
        "$chrome" \
            --remote-debugging-port="$CDP_PORT" \
            --user-data-dir="$USER_DATA_DIR" \
            --no-first-run \
            --no-default-browser-check \
            >/dev/null 2>&1 &
        echo "Chromium PID: $!  (kill with: kill $!)"

        # Wait up to 10s for the CDP endpoint to accept connections.
        local _i
        for _i in {1..20}; do
            if is_cdp_up; then
                break
            fi
            sleep 0.5
        done

        if ! is_cdp_up; then
            echo "Error: Chromium CDP did not come up within 10s on port ${CDP_PORT}" >&2
            return 1
        fi
        echo "Chromium CDP ready."
    fi

    export PLAYWRIGHT_CDP_ENDPOINT="http://localhost:${CDP_PORT}"
    echo "PLAYWRIGHT_CDP_ENDPOINT=${PLAYWRIGHT_CDP_ENDPOINT}"
    echo
}
