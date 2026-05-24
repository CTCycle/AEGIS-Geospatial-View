from __future__ import annotations

import pytest

from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition


def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="list_geospatial_capabilities",
        description="List catalog",
        parameters_json_schema={"type": "object", "properties": {}},
    )


def test_openai_converts_tool_definitions() -> None:
    schema = OpenAIProvider.tool_to_openai_schema(_tool())
    assert schema == {
        "type": "function",
        "function": {
            "name": "list_geospatial_capabilities",
            "description": "List catalog",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def test_openai_converts_assistant_tool_calls_and_tool_results() -> None:
    messages = OpenAIProvider.normalize_tool_messages(
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "list_geospatial_capabilities",
                        "arguments": {"limit": 5},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call-1",
                "name": "list_geospatial_capabilities",
                "content": "{\"ok\":true}",
            },
        ]
    )

    assert messages[0]["tool_calls"][0]["type"] == "function"
    assert messages[0]["tool_calls"][0]["function"]["name"] == "list_geospatial_capabilities"
    assert messages[1] == {
        "role": "tool",
        "tool_call_id": "call-1",
        "content": "{\"ok\":true}",
    }


def test_openai_rejects_tools_plus_response_schema() -> None:
    with pytest.raises(ValueError, match="cannot combine native tools"):
        LLMRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "x"}],
            tools=[_tool()],
            response_json_schema={"type": "object", "properties": {}},
        )

