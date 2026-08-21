from __future__ import annotations

from io import BytesIO
from urllib.error import HTTPError

from server.services.llm.ollama import OllamaProvider
from server.services.llm.types import LLMToolDefinition

###############################################################################
def _tool() -> LLMToolDefinition:
    return LLMToolDefinition(
        name="execute_geospatial_capability",
        description="Execute capability",
        parameters_json_schema={"type": "object", "properties": {}},
    )

###############################################################################
def test_ollama_uses_show_capabilities_when_present() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            assert path == "/api/show"
            return {"capabilities": ["completion", "tools"]}

    provider = _Provider(base_url="http://ollama.test")

    assert provider.supports_tools("llama") is True
    assert provider._tool_support_source("llama") == "ollama_show"
    assert provider.supports_structured_output("llama") is True
    assert "structured_output" in provider.get_model_capabilities("llama")

###############################################################################
def test_ollama_tag_capabilities_include_structured_output() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _get_json(self, path: str):
            assert path == "/api/tags"
            return {
                "models": [
                    {
                        "name": "llama",
                        "details": {"family": "llama"},
                        "capabilities": ["completion", "tools"],
                    }
                ]
            }

    provider = _Provider(base_url="http://ollama-tags.test")
    [model] = provider.list_models()

    assert "structured_output" in model.capabilities
    assert "tools" in model.capabilities

###############################################################################
def test_ollama_structured_requests_allow_the_longer_local_inference_window() -> None:
    provider = OllamaProvider(base_url="http://ollama.test")

    assert provider._STRUCTURED_REQUEST_TIMEOUT_SECONDS == 90
    assert provider._DEFAULT_REQUEST_TIMEOUT_SECONDS == 30

###############################################################################
def test_ollama_falls_back_to_probe_when_show_capabilities_absent() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
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

###############################################################################
def test_ollama_accepts_successful_tool_request_without_tool_call() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            if path == "/api/show":
                return {}
            assert path == "/api/chat"
            return {"message": {"content": "I can use tools when needed."}}

    provider = _Provider(base_url="http://ollama-accepted-tools.test")

    assert provider.supports_tools("llama") is True
    assert provider._tool_support_source("llama") == "ollama_tool_request_accepted"

###############################################################################
def test_ollama_rejects_explicit_unsupported_tool_error() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            if path == "/api/show":
                return {}
            assert path == "/api/chat"
            raise HTTPError(
                "http://ollama-no-tools.test/api/chat",
                400,
                "Bad Request",
                {},
                BytesIO(b'{"error":"model does not support tools"}'),
            )

    provider = _Provider(base_url="http://ollama-no-tools.test")

    assert provider.supports_tools("plain") is False
    assert provider._tool_support_source("plain") == "ollama_tool_request_rejected"

###############################################################################
def test_ollama_keeps_transport_probe_failure_unknown() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            if path == "/api/show":
                return {}
            raise TimeoutError("timed out")

    provider = _Provider(base_url="http://ollama-timeout.test")

    assert provider.supports_tools("plain") is None
    assert "tools" not in provider.get_model_capabilities("plain")

###############################################################################
def test_ollama_emits_native_tool_result_message_format() -> None:
    schema = OllamaProvider.tool_to_ollama_schema(_tool())
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "execute_geospatial_capability"

