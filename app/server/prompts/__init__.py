"""Canonical free-form model instructions used by the AEGIS backend."""

from server.prompts.agent import (
    build_native_context_messages,
    build_native_agent_system_prompt,
)
from server.prompts.context import build_compacted_history_summary
from server.prompts.providers import (
    OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT,
    build_deepseek_json_schema_instruction,
)

__all__ = [
    "OLLAMA_TOOL_CAPABILITY_PROBE_PROMPT",
    "build_compacted_history_summary",
    "build_deepseek_json_schema_instruction",
    "build_native_context_messages",
    "build_native_agent_system_prompt",
]
