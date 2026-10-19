from __future__ import annotations

from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMToolDefinition

###############################################################################
def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="resolve_location",
        description="Resolve location",
        parameters_json_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}},
        },
    )

###############################################################################
def test_provider_tool_schema_conversion() -> None:
    tool = _tool()
    openai_schema = OpenAIProvider.tool_to_openai_schema(tool)
    assert openai_schema["type"] == "function"
    assert openai_schema["name"] == "resolve_location"
    assert openai_schema["strict"] is True
    assert GoogleProvider.tool_to_google_schema(tool)["name"] == "resolve_location"
    assert (
        OllamaProvider.tool_to_ollama_schema(tool)["function"]["name"]
        == "resolve_location"
    )

###############################################################################
def test_openai_strict_schema_covers_nested_definitions_and_falls_back_for_free_form() -> None:
    nested = LLMToolDefinition(
        name="route",
        description="Route",
        parameters_json_schema={
            "type": "object",
            "properties": {"scope": {"$ref": "#/$defs/Scope"}},
            "$defs": {
                "Scope": {
                    "type": "object",
                    "properties": {"kind": {"type": "string"}, "rel": {"type": "string"}},
                    "required": ["kind"],
                }
            },
        },
    )
    free_form = LLMToolDefinition(
        name="route",
        description="Route",
        parameters_json_schema={
            "type": "object",
            "properties": {"filters": {"type": "object", "additionalProperties": True}},
        },
    )

    strict = OpenAIProvider.tool_to_openai_schema(nested)
    relaxed = OpenAIProvider.tool_to_openai_schema(free_form)

    assert strict["strict"] is True
    assert strict["parameters"]["$defs"]["Scope"]["required"] == ["kind", "rel"]
    assert strict["parameters"]["$defs"]["Scope"]["additionalProperties"] is False
    assert relaxed["strict"] is False
    assert relaxed["parameters"] == free_form.parameters_json_schema

###############################################################################
def test_tool_call_parsing() -> None:
    openai_calls = OpenAIProvider._parse_tool_calls(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "1",
                    "name": "resolve_location",
                    "arguments": '{"q":"Rome"}',
                }
            ]
        }
    )
    google_calls = GoogleProvider._parse_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "resolve_location",
                                    "args": {"q": "Rome"},
                                }
                            }
                        ]
                    }
                }
            ]
        }
    )
    ollama_calls = OllamaProvider._parse_tool_calls(
        {
            "tool_calls": [
                {
                    "id": "1",
                    "function": {
                        "name": "resolve_location",
                        "arguments": {"q": "Rome"},
                    },
                }
            ]
        }
    )
    assert openai_calls[0].arguments["q"] == "Rome"
    assert google_calls[0].name == "resolve_location"
    assert ollama_calls[0].arguments["q"] == "Rome"
