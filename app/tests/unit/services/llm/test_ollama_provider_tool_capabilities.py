from __future__ import annotations

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
    assert model.metadata["tool_support_source"] == "ollama_tags"

###############################################################################
def test_ollama_keeps_missing_tool_metadata_unknown_without_chat_inference() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def __init__(self) -> None:
            super().__init__(base_url="http://ollama-metadata-only.test")
            self.post_paths: list[str] = []

        # -------------------------------------------------------------------------
        def _get_json(self, path: str):
            assert path == "/api/tags"
            return {
                "models": [
                    {
                        "name": "plain",
                        "details": {"family": "custom"},
                    }
                ]
            }

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            self.post_paths.append(path)
            assert path == "/api/show"
            assert payload == {"name": "plain"}
            return {}

    provider = _Provider()
    [model] = provider.list_models()

    assert model.metadata["supports_tools"] is None
    assert model.metadata["tool_support_source"] == "unknown"
    assert "tools" not in model.capabilities
    assert provider.supports_tools("plain") is None
    assert provider.post_paths == ["/api/show"]

###############################################################################
def test_ollama_uses_tool_support_cached_from_runtime_without_a_probe() -> None:
    provider = OllamaProvider(base_url="http://ollama-runtime-cache.test")
    provider.tool_capability_cache.set(
        provider.base_url,
        "llama",
        True,
        source="runtime",
    )

    assert provider.supports_tools("llama") is True
    assert provider._tool_support_source("llama") == "runtime"

###############################################################################
def test_ollama_structured_requests_allow_the_longer_local_inference_window() -> None:
    provider = OllamaProvider(base_url="http://ollama.test")

    assert provider._STRUCTURED_REQUEST_TIMEOUT_SECONDS == 90
    assert provider._DEFAULT_REQUEST_TIMEOUT_SECONDS == 30

###############################################################################
def test_ollama_emits_native_tool_result_message_format() -> None:
    schema = OllamaProvider.tool_to_ollama_schema(_tool())
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "execute_geospatial_capability"

###############################################################################
def test_ollama_reads_context_window_only_from_show_metadata() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            assert path == "/api/show"
            assert payload == {"name": "runtime-model"}
            return {
                "model_info": {
                    "general.architecture": "llama",
                    "general.context_length": 8192,
                }
            }

    provider = _Provider(base_url="http://ollama-context.test")

    assert provider.get_model_context_metadata("runtime-model") == {
        "context_window_tokens": 8192,
        "context_profile_source": "ollama_show_model_info",
        "context_metadata_authority": "provider",
    }

###############################################################################
def test_ollama_does_not_infer_context_from_missing_or_malformed_metadata() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def __init__(self, payload: dict):
            super().__init__(base_url="http://ollama-context-empty.test")
            self.payload = payload

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            assert path == "/api/show"
            return self.payload

    assert _Provider({"model_info": {}}).get_model_context_metadata("custom-4k") == {}
    assert (
        _Provider(
            {"model_info": {"general.context_length": "not-a-number"}}
        ).get_model_context_metadata("custom-4k")
        == {}
    )

###############################################################################
def test_ollama_rejects_conflicting_show_context_metadata() -> None:

    ###############################################################################
    class _Provider(OllamaProvider):

        # -------------------------------------------------------------------------
        def _post_json(self, path: str, payload: dict):
            assert path == "/api/show"
            return {
                "context_length": 8192,
                "model_info": {"general.context_length": 16_384},
            }

    assert (
        _Provider(
            base_url="http://ollama-context-conflict.test"
        ).get_model_context_metadata("runtime-model")
        == {}
    )
