from __future__ import annotations

from server.services.llm.ollama import OllamaProvider
from server.services.llm.types import LLMToolDefinition


def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="execute_geospatial_capability",
        description="Execute capability",
        parameters_json_schema={"type": "object", "properties": {}},
    )


def test_ollama_uses_show_capabilities_when_present() -> None:
    class _Provider(OllamaProvider):
        def _post_json(self, path: str, payload: dict):
            assert path == "/api/show"
            return {"capabilities": ["completion", "tools"]}

    provider = _Provider(base_url="http://ollama.test")

    assert provider.supports_tools("llama") is True
    assert provider._tool_support_source("llama") == "ollama_show"


def test_ollama_falls_back_to_probe_when_show_capabilities_absent() -> None:
    class _Provider(OllamaProvider):
        def _post_json(self, path: str, payload: dict):
            if path == "/api/show":
                return {}
            assert path == "/api/chat"
            return {
                "message": {
                    "tool_calls": [
                        {
                            "id": "1",
                            "function": {
                                "name": "aegis_tool_probe",
                                "arguments": {},
                            },
                        }
                    ]
                }
            }

    provider = _Provider(base_url="http://ollama-probe.test")

    assert provider.supports_tools("llama") is True
    assert provider._tool_support_source("llama") == "ollama_probe"


def test_ollama_marks_unsupported_probe_false() -> None:
    class _Provider(OllamaProvider):
        def _post_json(self, path: str, payload: dict):
            if path == "/api/show":
                return {}
            return {"message": {"content": "no tool"}}

    provider = _Provider(base_url="http://ollama-no-tools.test")

    assert provider.supports_tools("plain") is False
    assert "tools" not in provider.get_model_capabilities("plain")


def test_ollama_emits_native_tool_result_message_format() -> None:
    schema = OllamaProvider.tool_to_ollama_schema(_tool())
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "execute_geospatial_capability"

