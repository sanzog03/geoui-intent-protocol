"""Hit each remote MCP URL once to absorb cold-start latency.

Two entry points share one implementation:

- CLI:    ``uv run python -m worldview.agents.warm_mcps``
          (used by ``start.sh`` at notebook launch)
- Python: ``from worldview.agents.warm_mcps import warm``
          (used by the marimo "Warm MCPs" button)

URLs are the remote servers of the plugin's ``.mcp.json`` that are enabled
by the keys in the environment (``worldview.plugin.load_mcp_config``), so
this stays in sync as servers are added, removed or unlocked.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv
from pydantic_ai.mcp import MCPServerSSE, MCPServerStreamableHTTP

from worldview.agents._common import load_servers
from worldview.plugin import LOCAL_SERVER_NAMES

_WARM_TIMEOUT_S = 15.0


@dataclass(frozen=True)
class WarmResult:
    """Outcome of a single warm-up request.

    Either ``status`` is set (an HTTP response came back — any status
    proves the container woke up) or ``error`` is set (transport
    failure: DNS, timeout, connection refused).
    """

    url: str
    status: int | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.status is not None


def _remote_mcp_urls() -> list[str]:
    """Every HTTP(S) MCP URL the agents will connect to (local and stdio
    servers excluded)."""
    return [
        server.url
        for name, server in load_servers().items()
        if name not in LOCAL_SERVER_NAMES and isinstance(server, MCPServerStreamableHTTP | MCPServerSSE)
    ]


async def _warm_one(client: httpx.AsyncClient, url: str) -> WarmResult:
    try:
        resp = await client.get(url, timeout=_WARM_TIMEOUT_S)
        return WarmResult(url=url, status=resp.status_code)
    except httpx.HTTPError as exc:
        return WarmResult(url=url, error=type(exc).__name__)


async def warm() -> list[WarmResult]:
    """Warm every remote MCP in the agent's default capability list.

    Returns one result per URL, in ``.mcp.json`` order. The marimo
    "Warm MCPs" cell consumes this directly; the CLI entry point
    formats it for console output.
    """
    urls = _remote_mcp_urls()
    if not urls:
        return []
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(*(_warm_one(client, url) for url in urls))


def _print_results(results: list[WarmResult]) -> None:
    if not results:
        print("No remote MCP URLs to warm.")
        return
    print(f"Warming {len(results)} MCP endpoint(s)...")
    for r in results:
        if r.ok:
            print(f"  {r.url} -> HTTP {r.status}")
        else:
            print(f"  {r.url} -> warm failed ({r.error})")


if __name__ == "__main__":
    load_dotenv()  # the keys decide which servers are enabled
    _print_results(asyncio.run(warm()))
