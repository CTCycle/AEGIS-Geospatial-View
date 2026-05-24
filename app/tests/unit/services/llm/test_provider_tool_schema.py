from __future__ import annotations

from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMToolDefinition


def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="resolve_location",
        description="Resolve location",
        parameters_json_schema={"type": "object", "properties": {"q": {"type": "string"}}},
    )


def test_provider_tool_schema_conversion() -> None:
    tool = _tool()
    openai_schema = OpenAIProvider.tool_to_openai_schema(tool)
    assert openai_schema["type"] == "function"
    assert openai_schema["function"]["name"] == "resolve_location"
    assert GoogleProvider.tool_to_google_schema(tool)["name"] == "resolve_location"
    assert OllamaProvider.tool_to_ollama_schema(tool)["function"]["name"] == "resolve_location"


def test_tool_call_parsing() -> None:
    openai_calls = OpenAIProvider._parse_tool_calls(
        {"output": [{"type": "function_call", "call_id": "1", "name": "resolve_location", "arguments": "{\"q\":\"Rome\"}"}]}
    )
    google_calls = GoogleProvider._parse_tool_calls(
        {"candidates": [{"content": {"parts": [{"functionCall": {"name": "resolve_location", "args": {"q": "Rome"}}}]}}]}
    )
    ollama_calls = OllamaProvider._parse_tool_calls(
        {"tool_calls": [{"id": "1", "function": {"name": "resolve_location", "arguments": {"q": "Rome"}}}]}
    )
    assert openai_calls[0].arguments["q"] == "Rome"
    assert google_calls[0].name == "resolve_location"
    assert ollama_calls[0].arguments["q"] == "Rome"
