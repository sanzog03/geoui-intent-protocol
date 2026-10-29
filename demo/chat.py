"""Multi-turn chat with a GeoUI demo agent.

One notebook, three agents, selected by the ``AGENT`` environment variable:

- ``geoui`` (default): the ``worldview-assistant`` Claude Code skill on a
  bare pydantic-ai agent. It speaks **GeoIntent** through the GeoUI
  protocol tools; the browser is only used to open the rendered URL and
  read the live URL back.
- ``vlm``: the non-GeoUI ``mio-worldviewagent-v2`` skill plus full
  Playwright browser control, the baseline. It observes NASA Worldview via
  screenshots + an accessibility-tree snapshot and acts by clicking,
  typing and dragging against the live page.
- ``maplibre``: the MapLibre demo's agent (``demo/maplibre``, an app with
  no URL state). Only the three GeoUI tools, served in-process over CDP by
  the ``maplibre`` package; no plugin, no remote MCPs, no browser tools.
  Needs the Vite dev server (``npm run dev``).

Same Chromium-on-CDP plumbing, same live tool-call trace, same
session/reset controls and benchmark logging; the agent is where the
divergence lives. Each turn passes the previous turns' messages back as
``message_history``, so the conversation has memory.

Run from the repo root (``demo/start.sh`` does all of this):

    ./demo/start.sh                                  # GeoUI treatment
    AGENT=vlm ./demo/start.sh                        # VLM baseline
    AGENT=maplibre ./demo/start.sh                   # MapLibre demo (npm run dev first)
    AGENT=vlm uv run marimo edit demo/chat.py   # editor

Requires `.env` with at minimum OPENAI_API_KEY and VECTOR_DB_TOOL_KEY
(see `.env.example`). The notebook auto-loads `.env` by walking up from
the cwd via python-dotenv. The Chromium launched by ``demo/start.sh`` is
agent-agnostic; both agents attach to the same CDP endpoint on port 9222.
"""

import marimo

__generated_with = "0.23.3"
app = marimo.App(width="medium")


@app.cell
def _setup_marimo():
    import marimo as mo

    return (mo,)


@app.cell
def _variant():
    """Pick the agent from ``AGENT`` (``geoui``, ``vlm`` or ``maplibre``; default ``geoui``).

    Everything that differs between the demo flavours lives in this one
    dict: the agent factory, the text-output class, whether the Worldview
    plugin and its remote MCPs are involved, the intro text and the example
    prompts. The rest of the notebook is variant-agnostic.
    """
    import os as _os  # private: ``os`` is also imported by the env cell

    from worldview.agents import TextOutput as _worldview_text_output
    from worldview.agents import geoui_agent, vlm_agent

    AGENT = _os.environ.get("AGENT", "geoui").strip().lower()
    if AGENT not in ("geoui", "vlm", "maplibre"):
        raise ValueError(f"AGENT must be 'geoui', 'vlm' or 'maplibre' (got {AGENT!r})")
    if AGENT == "maplibre":
        from maplibre.agents import build_maplibre_agent as _build_maplibre_agent
    else:
        _build_maplibre_agent = None

    geoui_intro = r"""
    # Worldview GeoUI Agent — Multi-turn Chat

    The `worldview-assistant` Claude Code skill (vendored under
    `demo/worldview/agents/artifact/worldview/geoui/`) running on a bare pydantic-ai agent. The
    agent speaks **GeoIntent** through the GeoUI Protocol tools
    (`geo_ui_render_intent_tool`, `geo_ui_get_state_tool`, served
    in-process from this repo) and gets Worldview permalink URLs back.
    Discovery tools are the plugin's remote MCP servers; the skill's
    `references/` documents are reachable through `read_reference`.

    **Browser scope:** `browser_navigate` to open the rendered URL and
    `browser_evaluate` to read `window.location.href` back. No
    screenshots, no clicks.

    ### One-time setup

    Launch Chromium with remote debugging **before** opening this
    notebook, and point `PLAYWRIGHT_CDP_ENDPOINT` at it (`demo/start.sh`
    does both):

    ```bash
    ./demo/start.sh
    ```

    Each agent turn attaches a fresh Playwright MCP to this
    already-running Chromium via CDP, so the map's URL / pan / zoom
    survives across turns even though the MCP itself doesn't.

    ### Using it

    - Type a query (e.g. *"Show Saharan dust over the Atlantic on 2023-06-15"*).
    - The agent may answer directly, ask a clarifying question, or
      render a URL via `geo_ui_render_intent_tool` once it has enough info.
    - After rendering, the agent calls `browser_navigate` to open the
      URL in your Chromium window. Pan, zoom, or scrub directly in
      the map — on the next turn the agent reads the live URL back
      via `browser_evaluate` and refines from there.
    """

    vlm_intro = r"""
    # Worldview VLM Agent — Multi-turn Chat

    The **baseline** for the token-efficiency comparison against the
    GeoUI Protocol: the non-GeoUI `mio-worldviewagent-v2` skill (vendored
    under `demo/worldview/agents/artifact/worldview/vlm/`) plus a browser addendum, on a bare pydantic-ai
    agent. Instead of a structured `GeoIntent`, this agent treats NASA
    Worldview the way a person would: it **looks at the page** (PNG
    screenshot + accessibility-tree snapshot) and **manipulates it**
    (click, type, press-key, drag). Each refining turn re-observes from
    pixels and DOM rather than parsing a permalink URL.

    **Browser scope (eleven tools):** `browser_snapshot`,
    `browser_take_screenshot`, `browser_click`, `browser_type`,
    `browser_press_key`, `browser_hover`, `browser_drag`,
    `browser_select_option`, `browser_wait_for`, `browser_navigate` (once,
    to open `worldview.earthdata.nasa.gov`) and a single end-of-turn
    `browser_evaluate("() => window.location.href")`.

    The discovery MCPs are identical to the GeoUI variant — the comparison
    holds discovery cost equal on purpose.

    ### One-time setup

    Same as the GeoUI variant: `./demo/start.sh` launches Chromium with
    remote debugging and sets `PLAYWRIGHT_CDP_ENDPOINT`.

    ### Using it

    - Type a query (e.g. *"Show MODIS Aqua Aerosol on 2025-09-15"*).
    - On the first turn you'll see it navigate to Worldview, take a
      snapshot, then click *+ Add Layers* and type the layer name.
    - Refining turns (*"zoom to Huntsville"*, *"compare with the
      following day"*) start with a fresh snapshot, then click / type / drag.
    - Watch the **Tool calls** collapsible mid-turn: this agent is meant
      to be chatty, but the once-per-turn observation budget in its
      prompt should keep it from looping. If it does loop, hit stop and
      the cleanup will cancel the background task.
    """

    maplibre_intro = r"""
    # MapLibre GeoUI Agent — Multi-turn Chat

    The GeoUI protocol on an application with **no URL state**: the
    MapLibre + NASA GIBS demo (`demo/maplibre`) attaches its React state to
    the protocol with the `@geoui/react-adapter` SDK and exposes `window.geoui`.
    The agent (`maplibre.agents.build_maplibre_agent`) is a bare
    pydantic-ai agent with only the three GeoUI tools
    (`geo_ui_list_intent_extensions_tool`, `geo_ui_get_state_tool`,
    `geo_ui_render_intent_tool`), served in-process by the `maplibre`
    package over Chrome DevTools Protocol. No plugin, no discovery MCPs, no
    browser tools: the page's own catalogue tells the agent which layers
    and extensions exist.

    ### One-time setup

    ```bash
    npm run dev        # the app at http://127.0.0.1:5173 (GEOUI_APP_URL)
    AGENT=maplibre ./demo/start.sh      # Chromium on CDP + this notebook
    ```

    The bridge opens the app in a tab of that Chromium on the first turn
    (or reuses one already at `GEOUI_APP_URL`). Nothing is navigated
    afterwards: each render writes the state into the page.

    ### Using it

    - Type a query (e.g. *"Show MODIS Aqua aerosol optical depth over
      California on 2025-09-15"*). Expect `list` then `render` on the first
      turn, `get_state` then `render` on refinements.
    - Pan, zoom or change layers by hand in the app between turns; the
      agent reads the live state back with `geo_ui_get_state_tool`.
    - Rendering replaces the whole state, so *"compare it to the previous
      day"* keeps the layer and date because the agent resends them.
    - Compare swipe and per-layer styling fields work; the chart extension
      is not attached, and the agent is told so if it tries.
    """

    VARIANT = {
        "geoui": {
            "build": geoui_agent.build_geoui_agent,
            "text_output": _worldview_text_output,
            "uses_plugin": True,
            "intro_md": geoui_intro,
            "example_prompts": [
                "I'd like to look at Saharan dust transport over the Atlantic on June 15, 2023.",
                "Show aerosol optical depth over California on September 15, 2025.",
                "What datasets do you have for sea-surface temperature?",
            ],
        },
        "vlm": {
            "build": vlm_agent.build_vlm_agent,
            "text_output": _worldview_text_output,
            "uses_plugin": True,
            "intro_md": vlm_intro,
            "example_prompts": [
                "Show MODIS Aqua Aerosol on 2025-09-15.",
                "Now zoom to Huntsville, Alabama.",
                "Compare with the following day.",
            ],
        },
        "maplibre": {
            "build": _build_maplibre_agent,
            "text_output": str,  # the MapLibre agent answers questions as plain text
            "uses_plugin": False,
            "intro_md": maplibre_intro,
            "example_prompts": [
                "Show MODIS Aqua aerosol optical depth over California on 2025-09-15.",
                "Compare it to the previous day with a swipe.",
                "Make the aerosol layer 60% opaque and add coastlines on top.",
            ],
        },
    }[AGENT]
    return AGENT, VARIANT


@app.cell
def _intro(VARIANT, mo):
    mo.md(VARIANT["intro_md"])


@app.cell
def _env(VARIANT, mo):
    """Load `.env` and surface missing required keys before any agent
    instantiation downstream. For the MapLibre variant the plugin keys do
    not apply; the app must be reachable at ``GEOUI_APP_URL`` instead.
    """
    import os

    from dotenv import load_dotenv

    load_dotenv()  # walks up from cwd; no-op if .env is missing

    required_keys = ["OPENAI_API_KEY"]
    missing_keys = [k for k in required_keys if not os.getenv(k)]

    unset_mcp_keys = []
    app_url_problem = None
    if VARIANT["uses_plugin"]:
        from worldview.plugin import env_var_for, plugin_dir, user_config_from_env

        # Optional: each unlocks a group of the plugin's MCP servers. Missing
        # ones are skipped by ``worldview.plugin.load_mcp_config`` with a warning.
        _root = plugin_dir()
        unset_mcp_keys = [env_var_for(k) for k, v in user_config_from_env(_root).items() if v is None]
    else:
        import httpx as _httpx

        _app_url = os.getenv("GEOUI_APP_URL") or "http://127.0.0.1:5173"
        try:
            _httpx.get(_app_url, timeout=3.0).raise_for_status()
        except _httpx.HTTPError as _exc:
            app_url_problem = f"{_app_url} ({type(_exc).__name__})"

    cdp_endpoint = os.getenv("PLAYWRIGHT_CDP_ENDPOINT")

    if missing_keys:
        env_status = mo.callout(
            mo.md(
                f"**Missing env vars:** `{', '.join(missing_keys)}`. "
                f"Create `.env` from `.env.example` in the repo root and re-run."
            ),
            kind="danger",
        )
    elif app_url_problem:
        env_status = mo.callout(
            mo.md(
                f"**The MapLibre demo is not answering at `{app_url_problem}`.** "
                "Start it with `npm run dev` (or set `GEOUI_APP_URL`) and re-run."
            ),
            kind="danger",
        )
        missing_keys = ["GEOUI_APP_URL"]  # no agent until the page exists
    elif not cdp_endpoint:
        env_status = mo.callout(
            mo.md(
                "**`PLAYWRIGHT_CDP_ENDPOINT` not set.** The agent will boot a "
                "fresh Chromium per turn and your map state will not survive "
                "between turns, which defeats the iterative comparison. Run "
                "`./demo/start.sh` (or launch Chrome with "
                "`--remote-debugging-port=9222` and export "
                "`PLAYWRIGHT_CDP_ENDPOINT=http://localhost:9222` manually) "
                "and re-run."
            ),
            kind="warn",
        )
    else:
        _note = (
            f" MCP servers needing `{', '.join(unset_mcp_keys)}` are disabled until you add those keys to `.env`."
            if unset_mcp_keys
            else ""
        )
        env_status = mo.callout(
            mo.md(f"Env OK — `PLAYWRIGHT_CDP_ENDPOINT={cdp_endpoint}` will be used.{_note}"),
            kind="success" if not unset_mcp_keys else "info",
        )
    env_status
    return missing_keys, cdp_endpoint


@app.cell
def _warm_button(VARIANT, mo):
    """Manual MCP warm-up trigger (plugin variants only; the MapLibre demo has no remote MCPs).

    The first call to a remote MCP after it has gone cold (FastMCP
    DNS-level suspension, Lambda cold-start) can take several
    seconds. ``start.sh`` warms them once at launch; this button
    lets you re-warm mid-session — useful before kicking off a query
    you care about timing.
    """
    warm_btn = mo.ui.run_button(label="Warm MCPs")
    warm_btn if VARIANT["uses_plugin"] else mo.md("")
    return (warm_btn,)


@app.cell
async def _warm_handler(mo, warm_btn):
    """React to the warm button. Idle until ``warm_btn.value`` flips
    to True on click, then call ``warm()`` and render one line per
    endpoint with its HTTP status (or transport-error class).

    Marimo cell bodies are top-level code (mid-cell ``return`` is a
    syntax error), so we compute ``out`` in an if/else chain and
    display it once at the end.
    """
    if not warm_btn.value:
        out = mo.md("")
    else:
        from worldview.agents.warm_mcps import warm

        results = await warm()
        if not results:
            out = mo.md("_No remote MCPs configured — nothing to warm._")
        else:
            lines = [f"**Warmed {len(results)} endpoint(s):**", ""]
            for r in results:
                if r.ok:
                    lines.append(f"- `{r.url}` → HTTP **{r.status}**")
                else:
                    lines.append(f"- `{r.url}` → warm failed ({r.error})")
            out = mo.md("\n".join(lines))
    out


@app.cell
def _agent(VARIANT, cdp_endpoint, missing_keys):
    """Build the selected agent. Per-turn MCP lifecycle; Chromium is held
    *outside* the notebook via CDP (see ``PLAYWRIGHT_CDP_ENDPOINT`` in
    the env cell). Each ``agent.run`` spawns a fresh Playwright MCP
    that attaches to the running Chromium and tears down cleanly when
    the run completes — anyio's same-task enter/exit rule stays
    satisfied because the MCP's scope is fully contained in the run
    task.
    """
    from pydantic_ai.capabilities import Hooks

    from worldview.agents.benchmark import new_session_id

    TextOutput = VARIANT["text_output"]

    # Session dict has to exist before the trace hook so the hook's
    # closure can append to ``current_turn_tools``.
    # ``history`` is the pydantic-ai message history passed back on every
    # run (conversation memory); ``usage`` is the running RunUsage tally
    # across turns, ``last_usage`` the most recent turn's.
    # ``log_session_id`` groups all log rows from this marimo session;
    # ``attempts`` increments on every ``_handler`` call (success +
    # error), so error turns get their own ``turn_index`` rather than
    # being silently skipped.
    session = {
        "history": [],
        "turns": 0,
        "attempts": 0,
        "log_session_id": new_session_id(),
        "last_output": None,
        "last_run_id": None,
        "last_usage": None,
        "usage": None,
        "cdp_endpoint": cdp_endpoint,
        "current_turn_tools": [],
    }

    # before_tool_execute fires once per model-issued tool call. We
    # record the names in order so the chat can render a collapsible
    # trace. The handler clears this list before each run.
    trace_hook = Hooks()

    @trace_hook.on.before_tool_execute
    async def _record_tool_call(ctx, *, call, tool_def, args):
        session["current_turn_tools"].append(tool_def.name)
        return args

    if missing_keys:
        agent = None
    else:
        agent = VARIANT["build"](cdp_endpoint=cdp_endpoint, extra_capabilities=[trace_hook])

    return TextOutput, agent, session


@app.cell
def _chat(AGENT, TextOutput, VARIANT, agent, mo, session):
    """The chat itself.

    Async handler, shared by both agents. All MCPs (Playwright + the
    plugin's remote servers) are spun up and torn down per run. Chromium state is preserved by attaching the
    Playwright MCP to an externally-owned Chromium via CDP, so the
    cheap thing (subprocess spawn + JSON-RPC handshake) happens each
    turn while the expensive thing (Chromium launch + page render) is
    one-shot at the start of the session.
    """

    def _flatten_exceptions(exc: BaseException) -> list[BaseException]:
        """Recursively flatten ExceptionGroup into its leaf exceptions."""
        if isinstance(exc, BaseExceptionGroup):
            leaves: list[BaseException] = []
            for sub in exc.exceptions:
                leaves.extend(_flatten_exceptions(sub))
            return leaves
        return [exc]

    def _format_tool_trace(tools: list[str]) -> str:
        """Render an ordered tool-call trace as a collapsible details block.

        Empty string when no tools were called this turn — keeps simple
        clarification replies clean.
        """
        if not tools:
            return ""
        items = "\n".join(f"{i}. `{name}`" for i, name in enumerate(tools, 1))
        suffix = "" if len(tools) == 1 else "s"
        return f"\n\n<details><summary>Tool trace ({len(tools)} call{suffix})</summary>\n\n{items}\n\n</details>"

    def _format_error(exc: BaseException) -> str:
        """Format an exception (including ExceptionGroup) as a markdown
        block listing the leaf cause(s) plus the head of each traceback.
        """
        import traceback

        leaves = _flatten_exceptions(exc)
        if not leaves:
            return f"**Error:** {type(exc).__name__}: {exc}"

        sections = [f"**Error:** {len(leaves)} underlying exception(s)"]
        for i, leaf in enumerate(leaves, 1):
            tb_text = "".join(traceback.format_exception(type(leaf), leaf, leaf.__traceback__))
            # Trim very long tracebacks to keep the chat usable.
            if len(tb_text) > 1500:
                tb_text = tb_text[-1500:]
                tb_text = "  …\n" + tb_text
            sections.append(
                f"\n**[{i}] {type(leaf).__name__}:** {leaf}\n\n"
                f"<details><summary>Traceback</summary>\n\n```\n{tb_text}\n```\n\n</details>"
            )
        return "\n".join(sections)

    import asyncio
    import time
    import uuid

    from pydantic_ai.exceptions import ModelAPIError
    from pydantic_ai.usage import RunUsage, UsageLimits

    from worldview.agents import REQUEST_LIMIT
    from worldview.agents.benchmark import (
        ErrorRecord,
        TurnRecord,
        append_error_record,
        append_turn_record,
        extract_usage,
    )

    def _is_connection_error(exc: BaseException) -> bool:
        """Whether ``exc`` (or any leaf in its ``ExceptionGroup``) is a
        ``ModelAPIError: Connection error.`` from pydantic_ai.

        pydantic_ai wraps OpenAI's ``APIConnectionError`` (httpx-layer
        TCP / TLS failure) and stamps the bare message
        ``"Connection error."``. We match on both the class and the
        message so unrelated ``ModelAPIError`` cases (rate limits,
        5xx, etc.) don't trigger an auto-retry. MCP-init timeouts
        (``mcp.py:748``) are NOT connection errors — they need real
        attention, not a silent retry.
        """
        for leaf in _flatten_exceptions(exc):
            if isinstance(leaf, ModelAPIError) and "connection error" in str(leaf).lower():
                return True
        return False

    def _deepest_in_chain(exc: BaseException) -> BaseException:
        """Walk the exception chain (``__cause__`` *or* ``__context__``)
        to the deepest reachable exception.

        Python's chained-exception machinery uses two fields:
        ``__cause__`` is set by ``raise X from Y``; ``__context__`` is
        set implicitly when one exception is raised while handling
        another ("During handling of the above exception …"). Many of
        the failure modes we care about — ``asyncio.CancelledError`` →
        ``TimeoutError`` from ``anyio.fail_after``, or ``WouldBlock``
        → ``CancelledError`` from the MCP client — are stitched via
        ``__context__``, not ``__cause__``. Walking both lets us
        actually reach the underlying ``TimeoutError`` /
        ``ConnectError`` / ``ReadError`` instead of stopping at the
        outer ``ExceptionGroup`` leaf.
        """
        cur = exc
        seen: set[int] = {id(cur)}
        while True:
            nxt = cur.__cause__ or cur.__context__
            if nxt is None or id(nxt) in seen:
                return cur
            seen.add(id(nxt))
            cur = nxt

    def _underlying_cause_summary(exc: BaseException) -> str:
        """Format the deepest cause of ``exc`` as ``"ClassName: message"``.

        Used both for the in-chat retry notice and for the
        ``ErrorRecord.underlying_cause`` log field. Returns the
        sentinel string ``"(no underlying cause)"`` only when there's
        literally no chain to descend and the top-level exception
        carries no useful information (rare).
        """
        for leaf in _flatten_exceptions(exc):
            deepest = _deepest_in_chain(leaf)
            if deepest is not leaf:
                msg = str(deepest).strip() or "(empty)"
                return f"{type(deepest).__name__}: {msg}"
        # Fall back to the first leaf itself so we surface *something*
        # actionable — better than ``None`` in the log.
        leaves = _flatten_exceptions(exc)
        if leaves:
            leaf = leaves[0]
            msg = str(leaf).strip() or "(empty)"
            return f"{type(leaf).__name__}: {msg}"
        return "(no underlying cause)"

    async def _handler(messages, config):
        """Streaming handler with live tool-call visibility.

        Streams a collapsible ``<details><summary>Tool calls</summary>``
        block whose contents grow as ``before_tool_execute`` fires. The
        user can expand it mid-turn to see whether the agent is making
        progress or has entered a loop — that visibility is what makes
        manual stop usable.

        Tradeoffs we're explicitly accepting:

        - Marimo's chat-streaming protocol can raise
          ``Received text-delta for missing text part`` under heavy
          chunking. We mitigate by polling slowly (0.5s) and batching
          every new tool fired since the last poll into a single yield,
          which keeps the chunk count to ~one per second.
        - ``asyncio.create_task`` detaches ``agent.run`` from this
          generator's task. If the user hits stop, marimo closes the
          generator and we'd leak a background task that keeps firing
          tools. The ``finally`` block below cancels ``run_task`` on any exit
          (normal, error, or ``GeneratorExit``).
        """
        if agent is None:
            yield "Agent not initialised — fix the missing env vars above and re-run the notebook."
            return

        latest = messages[-1].content if messages else ""

        # Retry loop: at most one auto-retry on
        # ``ModelAPIError: Connection error.`` (i.e. httpx-layer TCP /
        # TLS failure to api.openai.com). One extra attempt absorbs
        # transient OpenAI / network hiccups without masking persistent
        # problems — any other error class falls straight through.
        # Each attempt logs its own benchmark row (the first as
        # ``output_kind="error"``, the second whichever way it lands)
        # so the underlying flake rate stays visible in the data.
        for retry_attempt in range(2):
            # Reset per-turn tool trace. The hook in _agent appends to
            # this list on each before_tool_execute fire.
            session["current_turn_tools"] = []

            # Bump attempt counter immediately so error turns get a
            # unique turn_index in the log even if the run fails before
            # ``session["turns"]`` (successful turns) advances.
            session["attempts"] += 1
            t_start = time.monotonic()
            run_id = str(uuid.uuid4())

            run_task = asyncio.create_task(
                agent.run(
                    latest,
                    message_history=list(session["history"]),
                    # Per-turn request cap (runaway protection). Usage is
                    # per run, so the cap never trips on cumulative counts;
                    # the cross-turn tally is kept in ``session["usage"]``.
                    usage_limits=UsageLimits(request_limit=REQUEST_LIMIT),
                    # Bump OpenAI HTTP timeout from the SDK default
                    # (10 min) to 15 min so large VLM payloads
                    # (multi-snapshot turns) have headroom before httpx
                    # surfaces a ``Connection error.``; harmless when
                    # responses arrive fast.
                    model_settings={"timeout": 900},
                )
            )

            details_opened = False
            last_count = 0

            def _flush_new_tools() -> str:
                """Build a chunk for any tools recorded since the last yield.

                Empty string when no new tools fired this tick. Opens
                the ``<details>`` block lazily on the first tool so
                turns that never call a tool don't render an empty
                collapsible.
                """
                nonlocal details_opened, last_count
                tools = list(session["current_turn_tools"])
                if len(tools) <= last_count:
                    return ""
                chunk = ""
                if not details_opened:
                    # Closed by default — Gemini-style "show thinking" toggle.
                    chunk = "<details><summary>Tool calls</summary>\n\n"
                    details_opened = True
                new = tools[last_count:]
                chunk += "".join(f"{i}. `{n}`\n" for i, n in enumerate(new, last_count + 1))
                last_count = len(tools)
                return chunk

            try:
                # Poll the trace list while the run runs. 0.5s timeout
                # keeps this cooperative without flooding the marimo
                # wire protocol. asyncio.wait doesn't cancel the task
                # on timeout — it just bounds how long we wait before
                # checking again.
                while not run_task.done():
                    await asyncio.wait({run_task}, timeout=0.5)
                    chunk = _flush_new_tools()
                    if chunk:
                        yield chunk

                # Drain anything that fired in the final tick.
                chunk = _flush_new_tools()
                if chunk:
                    yield chunk

                closer = "\n</details>\n" if details_opened else ""
                sep = "\n---\n\n" if details_opened else ""

                result = None
                output = None
                turn_error: BaseException | None = None
                try:
                    result = run_task.result()
                    output = result.output
                except BaseException as exc:  # noqa: BLE001 — surface ExceptionGroup too
                    turn_error = exc

                wall_clock = time.monotonic() - t_start
                turn_usage = result.usage if result is not None else None  # a property in pydantic-ai 2.x

                # Build + write benchmark log row. We log success and
                # error turns uniformly; the distinguishing field is
                # ``output_kind``.
                if turn_error is not None:
                    output_kind = "error"
                    final_url = None
                    error_type = type(turn_error).__name__
                    error_message = str(turn_error)[:500]
                elif isinstance(output, TextOutput):
                    output_kind = "text"
                    final_url = None
                    error_type = None
                    error_message = None
                else:
                    output_kind = "structured"
                    final_url = getattr(output, "url", None)
                    error_type = None
                    error_message = None

                try:
                    append_turn_record(
                        TurnRecord(
                            agent=AGENT,
                            session_id=session["log_session_id"],
                            run_id=run_id,
                            turn_index=session["attempts"],
                            user_prompt=latest,
                            tool_calls=list(session["current_turn_tools"]),
                            tool_call_count=len(session["current_turn_tools"]),
                            wall_clock_s=round(wall_clock, 3),
                            usage=extract_usage(turn_usage),
                            output_kind=output_kind,
                            final_url=final_url,
                            error_type=error_type,
                            error_message=error_message,
                        )
                    )
                except Exception:  # noqa: BLE001 — never let logging break the chat
                    pass

                if turn_error is not None:
                    # Append a detailed error log row (full traceback +
                    # underlying-cause chain). Done on every error
                    # turn, retried or not — pair with TurnRecord on
                    # ``session_id`` + ``turn_index`` for analysis.
                    try:
                        import traceback as _tb

                        _tb_text = "".join(_tb.format_exception(type(turn_error), turn_error, turn_error.__traceback__))
                        _cause = _underlying_cause_summary(turn_error)
                        append_error_record(
                            ErrorRecord(
                                agent=AGENT,
                                session_id=session["log_session_id"],
                                turn_index=session["attempts"],
                                retry_attempt=retry_attempt,
                                user_prompt=latest,
                                error_type=type(turn_error).__name__,
                                error_message=str(turn_error),
                                # _underlying_cause_summary now falls
                                # back to the first leaf when there's
                                # no chain; only the truly-empty
                                # sentinel needs ``None``.
                                underlying_cause=_cause if _cause != "(no underlying cause)" else None,
                                traceback=_tb_text,
                                tool_calls=list(session["current_turn_tools"]),
                                tool_call_count=len(session["current_turn_tools"]),
                                wall_clock_s=round(wall_clock, 3),
                            )
                        )
                    except Exception:  # noqa: BLE001 — never let logging break the chat
                        pass

                    # Retry once on ``Connection error.``; otherwise
                    # surface the error and bail. The underlying-cause
                    # summary tells us which httpx failure mode hit
                    # (ConnectError / ReadError / RemoteProtocolError /
                    # WriteError) so subsequent failures are actionable.
                    if retry_attempt == 0 and _is_connection_error(turn_error):
                        cause = _underlying_cause_summary(turn_error)
                        yield (
                            closer
                            + sep
                            + "\n**Connection error to OpenAI** "
                            + f"(underlying: `{cause}`). Retrying in 2 s…\n\n"
                        )
                        await asyncio.sleep(2)
                        continue  # next retry_attempt
                    yield closer + sep + _format_error(turn_error)
                    return

                # Persist the conversation for the next turn.
                session["history"] = result.all_messages()
                session["turns"] += 1
                session["last_output"] = output
                session["last_run_id"] = run_id
                session["last_usage"] = turn_usage
                session["usage"] = (session.get("usage") or RunUsage()) + turn_usage

                if isinstance(output, TextOutput):
                    body = output if isinstance(output, str) else output.content
                else:
                    # Structured final output: render `result` markdown + clickable url.
                    # ``str(output)`` would give the Pydantic repr with escaped \n.
                    lines = [output.result.strip()]
                    url = getattr(output, "url", "") or ""
                    if url.strip():  # the MapLibre agent reports no URL: the view is already on screen
                        lines.append(f"\n**Worldview URL:** [{url}]({url})")
                    body = "\n".join(lines)

                yield closer + sep + body
                return
            finally:
                # Cancel the detached run_task on any exit path
                # (normal, exception, or generator close from a "stop"
                # click). Without this, hitting stop leaves the agent
                # firing tools in the background.
                if not run_task.done():
                    run_task.cancel()
                    try:
                        await run_task
                    except BaseException:  # noqa: BLE001 — swallow cancel propagation
                        pass

    chat = mo.ui.chat(_handler, prompts=VARIANT["example_prompts"])
    chat
    return (chat,)


@app.cell
def _session_view(chat, mo, session):
    """Reactive view of session state — re-renders after every turn
    because it depends on `chat` (which updates on each message).
    """
    _ = chat  # reactive trigger

    turns = session.get("turns", 0)
    last = session.get("last_output")

    def _format_last(obj):
        if obj is None:
            return "_(no output yet)_"
        cls_name = type(obj).__name__
        if hasattr(obj, "model_dump_json"):
            try:
                snippet = obj.model_dump_json(indent=2, exclude_none=True)
                if len(snippet) > 800:
                    snippet = snippet[:800] + "\n  …"
                return f"`{cls_name}`\n\n```json\n{snippet}\n```"
            except Exception:  # noqa: BLE001
                pass
        return f"`{cls_name}`: {obj}"

    last_usage_str = str(session.get("last_usage") or "n/a")
    run_id_str = session.get("last_run_id") or "n/a"
    cum_usage_str = str(session.get("usage") or "n/a")

    from worldview.agents.benchmark import DEFAULT_LOG_PATH

    log_session = session.get("log_session_id", "n/a")
    attempts = session.get("attempts", 0)

    mo.md(
        f"""
        ### Session state

        - **Turns:** {turns}
        - **Attempts (logged):** {attempts}
        - **Log session id:** `{log_session}`
        - **Log file:** `{DEFAULT_LOG_PATH}`
        - **Last `run_id`:** `{run_id_str}`
        - **Last turn usage:** `{last_usage_str}`
        - **Cumulative usage:** `{cum_usage_str}`

        #### Last output

        {_format_last(last)}
        """
    )


@app.cell
def _reset_controls(mo, session):
    """Reset the conversation memory without restarting the kernel."""
    reset = mo.ui.run_button(label="Reset conversation memory")
    reset
    return (reset,)


@app.cell
def _reset_handler(mo, reset, session):
    if reset.value:
        # Aliased to ``_new_session_id`` so marimo doesn't flag this
        # cell as a duplicate definition of ``new_session_id``
        # (which is also imported by the ``_agent`` cell for the
        # initial session-id assignment).
        from worldview.agents.benchmark import new_session_id as _new_session_id

        session["history"] = []
        session["turns"] = 0
        session["attempts"] = 0
        session["log_session_id"] = _new_session_id()
        session["last_output"] = None
        session["last_run_id"] = None
        session["last_usage"] = None
        session["usage"] = None
        mo.md("_Session memory cleared. Next message starts a fresh conversation._")
    else:
        mo.md("")


if __name__ == "__main__":
    app.run()
