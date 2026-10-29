"""Print an MCP server's tool contract (names, schemas, descriptions) as JSON.

Use it to diff the standalone server against the hosted akd-ext deployment,
or against the golden fixture in ``demo/worldview/tests/mcp/fixtures/akd_contract.json``.

Examples::

    # in-process (no server needed)
    uv run python scripts/dump_mcp_contract.py local

    # a running HTTP server
    uv run python scripts/dump_mcp_contract.py http://127.0.0.1:8000/mcp

    # the hosted deployment (bearer token from MCP_BEARER_TOKEN)
    MCP_BEARER_TOKEN=... uv run python scripts/dump_mcp_contract.py \
        https://sudden-gold-carp-feature-geoui-mcp-tools.fastmcp.app/mcp

    # only the protocol tools, then diff against the golden
    uv run python scripts/dump_mcp_contract.py local --only geo_ui_ > /tmp/ours.json

    # rewrite the golden from the in-process server (deliberate contract change; review the diff)
    uv run python scripts/dump_mcp_contract.py local --update-golden
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from fastmcp import Client


async def dump(target: str, only: str | None) -> dict:
    if target == "local":
        from worldview.mcp.server import mcp

        transport = mcp
    elif target.startswith("http"):
        from fastmcp.client.transports import StreamableHttpTransport

        headers = {}
        if token := os.getenv("MCP_BEARER_TOKEN"):
            headers["Authorization"] = f"Bearer {token}"
        transport = StreamableHttpTransport(target, headers=headers)
    else:
        transport = target  # a .py path → stdio

    async with Client(transport) as client:
        tools = await client.list_tools()

    return {
        t.name: {
            "name": t.name,
            "description": t.description,
            "inputSchema": t.inputSchema,
            "outputSchema": t.outputSchema,
        }
        for t in sorted(tools, key=lambda t: t.name)
        if only is None or t.name.startswith(only)
    }


GOLDEN = Path(__file__).resolve().parents[1] / "demo" / "worldview" / "tests" / "mcp" / "fixtures" / "akd_contract.json"


def update_golden(contract: dict) -> None:
    """Rewrite the contract fixture, keeping its akd-era keys: ``akd_description`` mirrors ``description``
    and ``akd_params`` lists the input parameter names; the akd ``_response`` output key stays absent."""
    golden = json.loads(GOLDEN.read_text()) if GOLDEN.exists() else {}
    for name, tool in contract.items():
        entry = golden.get(name, {})
        entry.update(tool)
        entry["akd_description"] = tool["description"]
        entry["akd_params"] = list((tool["inputSchema"] or {}).get("properties", {}))
        golden[name] = entry
    for name in list(golden):
        if name not in contract:
            del golden[name]
    GOLDEN.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {GOLDEN}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="'local' (in-process), an http(s) URL, or a server .py path (stdio)")
    parser.add_argument("--only", help="keep only tools whose name starts with this prefix")
    parser.add_argument("--update-golden", action="store_true", help="rewrite the test fixture from this contract")
    args = parser.parse_args(argv)
    contract = asyncio.run(dump(args.target, args.only or ("geo_ui_" if args.update_golden else None)))
    if args.update_golden:
        update_golden(contract)
        return
    json.dump(contract, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
