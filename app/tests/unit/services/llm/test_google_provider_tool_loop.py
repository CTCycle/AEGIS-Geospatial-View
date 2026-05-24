from __future__ import annotations

import pytest

from server.services.llm.google_provider import GoogleProvider
from server.services.llm.types import LLMRequest, LLMToolDefinition


def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="describe_geospatial_capability",
        description="Describe capability",
        parameters_json_schema={
            "type": "object",
            "properties": {"capability_id": {"type": "string"}},
            "required": ["capability_id"],
        },
    )


def test_google_converts_aegis_tools_into_declarations() -> None:
    assert GoogleProvider.tool_to_google_schema(_tool()) == {
        "name": "describe_geospatial_capability",
        "description": "Describe capability",
        "parameters": {
            "type": "object",
            "properties": {"capability_id": {"type": "string"}},
            "required": ["capability_id"],
        },
    }


def test_google_parses_function_calls() -> None:
    calls = GoogleProvider._parse_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "id": "1",
                                    "name": "describe_geospatial_capability",
                                    "args": {"capability_id": "rain"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert calls[0].name == "describe_geospatial_capability"
    assert calls[0].arguments == {"capability_id": "rain"}


def test_google_converts_tool_results_to_function_responses() -> None:
    contents = GoogleProvider._contents_from_messages(
        [
            {
                "role": "tool",
                "name": "describe_geospatial_capability",
                "tool_call_id": "1",
                "content": "{\"ok\":true}",
            }
        ]
    )

    assert contents == [
        {
            "role": "user",
            "parts": [
                {
                    "function_response": {
                        "name": "describe_geospatial_capability",
                        "response": {"content": "{\"ok\":true}"},
                    }
                }
            ],
        }
    ]


def test_google_rejects_tools_plus_response_schema() -> None:
    with pytest.raises(ValueError, match="cannot combine native tools"):
        LLMRequest(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            tools=[_tool()],
            response_json_schema={"type": "object", "properties": {}},
        )

