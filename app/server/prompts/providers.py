"""Provider-specific prompt declarations and protocol translations."""

from __future__ import annotations

import json
from typing import Any

DEEPSEEK_JSON_SCHEMA_TEMPLATE = (
    "Return JSON only. The response must match this JSON schema:\n{schema_json}"
)

OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT = (
    "Call the aegis_tool_probe tool with empty arguments."
)


###############################################################################
def build_deepseek_json_schema_instruction(schema: dict[str, Any]) -> str:
    return DEEPSEEK_JSON_SCHEMA_TEMPLATE.format(
        schema_json=json.dumps(schema, ensure_ascii=True, separators=(",", ":")),
    )
