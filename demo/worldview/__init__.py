"""NASA Worldview reference implementation of the GeoUI Intent Protocol.

Everything here is specific to Worldview and is kept out of the ``geoui``
library on purpose:

- ``worldview.adapter`` — ``GeoIntent`` ⇄ Worldview permalink URL.
- ``worldview.tools``   — the two protocol operations as plain async
  functions (``geo_ui_render_intent_tool`` / ``geo_ui_get_state_tool``)
  and, in ``worldview.tools.akd``, their akd ``BaseTool`` wrappers.
- ``worldview.mcp``     — FastMCP server exposing the two tools.
- ``worldview.agents``  — the IESO GeoUI (treatment) and VLM (baseline)
  agents, MCP warm-up and the benchmark logger.

Installed editable as the ``geoui-worldview-demo`` uv workspace member.
"""
