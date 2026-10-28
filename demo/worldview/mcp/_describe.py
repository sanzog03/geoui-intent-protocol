"""Tool-description builder compatible with the original akd-ext deployment.

akd's ``BaseTool`` appends an ``INPUT FIELD DESCRIPTIONS`` / ``OUTPUT FIELD
DESCRIPTIONS`` block (one bullet per schema field) to a tool's docstring.
The hosted GeoUI MCP server was built on that, so clients and logs have seen
this exact shape. Reproducing it keeps the standalone server a drop-in
replacement.
"""

from __future__ import annotations

from pydantic import BaseModel


def _field_lines(model: type[BaseModel]) -> str:
    return "\n".join(
        f"- **{name}**: {field.description or name.replace('_', ' ')}" for name, field in model.model_fields.items()
    )


def describe(doc: str, input_model: type[BaseModel], output_model: type[BaseModel]) -> str:
    """Return ``doc`` plus the akd-style field-description blocks."""
    text = doc.strip()
    if in_info := _field_lines(input_model):
        text += f"\n\nINPUT FIELD DESCRIPTIONS:\n{in_info}"
    if out_info := _field_lines(output_model):
        text += f"\n\nOUTPUT FIELD DESCRIPTIONS:\n{out_info}"
    return text


__all__ = ["describe"]
