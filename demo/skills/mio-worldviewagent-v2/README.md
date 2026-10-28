# mio-worldviewagent-v2 (vendored skill)

The non-GeoUI Worldview assistant skill, used as the system prompt of the
baseline agent (`worldview.agents.vlm_agent`). It discovers layers through
the same MCP tools as the GeoUI skill but builds permalinks with
`worldview_permalink_tool`; it has no notion of the GeoUI protocol.

Origin: exported from the CARE workspace as `mio-worldviewagent-v2-skill-vlm.zip`
(instance `bc336add-ddc8-4aeb-9fd2-1d46e3d2cd45`, exported 2026-10-28T02:08:52Z).
Only `SKILL.md` and `references/` are vendored. The export's `assets/`
(catalog and story mirrors, ~1,500 JSON files) and `.docx` files are omitted;
the same assets ship with the `worldview-assistant` plugin under
`demo/vendor/akd-plugins`.

To update: re-export the skill, replace `SKILL.md` and `references/`, and
regenerate `demo/worldview/tests/agents/fixtures/agent_surface.json`.
