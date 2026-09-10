from __future__ import annotations

from types import SimpleNamespace

from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.openai_provider import OpenAIProvider


def test_openai_preserves_invalid_json_and_real_empty_object() -> None:
    calls = OpenAIProvider._parse_tool_calls(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "bad",
                    "name": "resolve",
                    "arguments": "{not-json",
                },
                {
                    "type": "function_call",
                    "call_id": "empty",
                    "name": "resolve",
                    "arguments": {},
                },
            ]
        }
    )

    assert calls[0].arguments is None
    assert calls[0].parse_error == "invalid_json"
    assert calls[1].arguments == {}
    assert calls[1].parse_error is None


def test_google_and_ollama_reject_non_object_arguments() -> None:
    google_calls = GoogleProvider._parse_tool_calls(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "resolve",
                                    "args": ["not", "an", "object"],
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
                    "id": "call-1",
                    "function": {"name": "resolve", "arguments": "[]"},
                }
            ]
        }
    )

    assert google_calls[0].arguments is None
    assert google_calls[0].parse_error == "arguments_not_object"
    assert ollama_calls[0].arguments is None
    assert ollama_calls[0].parse_error == "arguments_not_object"


def test_deepseek_preserves_missing_name_as_a_parse_error() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(name="", arguments="{}"),
                        )
                    ],
                )
            )
        ]
    )

    _content, calls = DeepSeekProvider(api_key="test")._parse_choice(response)

    assert calls[0].name == ""
    assert calls[0].arguments == {}
    assert calls[0].parse_error == "missing_name"
