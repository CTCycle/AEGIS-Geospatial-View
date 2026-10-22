from __future__ import annotations
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.ollama import OllamaProvider
from server.services.llm.types import LLMToolDefinition, LLMRequest
from time import monotonic
import pytest
from server.services.llm.request_deadline import remaining_request_seconds
from types import SimpleNamespace
from server.services.llm.errors import LLMProviderRequestError, safe_failure_detail
from server.services.llm.transport import LLMTransportPolicy

# --- test_ollama_capability_cache.py ---


###############################################################################
def test_cache_hit_before_ttl_expiry() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=10.0)
    cache.set("http://localhost:11434", "llama3.2", True, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=105.0) is True

###############################################################################
def test_cache_expires_after_ttl() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=5.0)
    cache.set("http://localhost:11434", "llama3.2", False, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=106.0) is None

###############################################################################
def test_models_do_not_share_cache_records() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=20.0)
    cache.set("http://localhost:11434", "model-a", True, now=100.0)
    cache.set("http://localhost:11434", "model-b", False, now=100.0)
    assert cache.get("http://localhost:11434", "model-a", now=101.0) is True
    assert cache.get("http://localhost:11434", "model-b", now=101.0) is False

###############################################################################
def test_base_urls_do_not_share_cache_records() -> None:
    cache = OllamaToolCapabilityCache(ttl_seconds=20.0)
    cache.set("http://localhost:11434", "llama3.2", True, now=100.0)
    cache.set("http://127.0.0.1:11434", "llama3.2", False, now=100.0)
    assert cache.get("http://localhost:11434", "llama3.2", now=101.0) is True
    assert cache.get("http://127.0.0.1:11434", "llama3.2", now=101.0) is False

# --- test_ollama_provider_tool_capabilities.py ---


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

# --- test_request_deadline.py ---




###############################################################################
class _Provider(OllamaProvider):

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        super().__init__(base_url="http://ollama-deadline.test")
        self.post_calls = 0
        self.stream_calls = 0

    # -------------------------------------------------------------------------
    def _post_json(self, path: str, payload: dict, **kwargs):  # noqa: ANN003, ANN201
        self.post_calls += 1
        return {}

    # -------------------------------------------------------------------------
    def _stream_post(self, path: str, payload: dict, **kwargs):  # noqa: ANN003, ANN201
        self.stream_calls += 1
        yield {}

###############################################################################
def _expired_request() -> LLMRequest:
    return LLMRequest(
        model="runtime-model",
        messages=[],
        metadata={"deadline_monotonic": monotonic() - 1.0},
    )

###############################################################################
def test_expired_ollama_request_never_starts_transport() -> None:
    provider = _Provider()
    request = _expired_request()

    with pytest.raises(TimeoutError):
        provider._post_json_for_request("/api/chat", {}, request)
    with pytest.raises(TimeoutError):
        list(provider._stream_post_for_request("/api/chat", {}, request))

    assert provider.post_calls == 0
    assert provider.stream_calls == 0

###############################################################################
@pytest.mark.parametrize("value", [None, True, False, "not-a-number", float("nan")])
def test_invalid_deadline_metadata_is_not_treated_as_a_bound(value) -> None:
    request = LLMRequest(
        model="runtime-model",
        messages=[],
        metadata={"deadline_monotonic": value},
    )

    assert remaining_request_seconds(request) is None

# --- test_transport_policy.py ---




###############################################################################
def test_transport_policy_controls_timeout_retry_proxy_and_environment() -> None:
    policy = LLMTransportPolicy(
        request_timeout_seconds=11.0,
        catalog_timeout_seconds=3.0,
        stream_timeout_seconds=19.0,
        structured_timeout_seconds=23.0,
        max_attempts=4,
        retry_backoff_base_seconds=0.5,
        retry_backoff_max_seconds=1.5,
        proxy="http://proxy.test:8080",
        trust_env=False,
    )

    assert policy.timeout_for("chat") == 11.0
    assert policy.timeout_for("catalog") == 3.0
    assert policy.timeout_for("stream") == 19.0
    assert policy.timeout_for("structured_output") == 23.0
    assert policy.retry_delay(1) == 0.5
    assert policy.retry_delay(4) == 1.5
    assert policy.httpx_options("chat") == {
        "timeout": 11.0,
        "trust_env": False,
        "proxy": "http://proxy.test:8080",
    }
    assert policy.client_args() == {
        "trust_env": False,
        "proxy": "http://proxy.test:8080",
    }

###############################################################################
def test_transport_policy_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        LLMTransportPolicy(max_attempts=0)
    with pytest.raises(ValueError, match="proxy"):
        LLMTransportPolicy(proxy=42)  # type: ignore[arg-type]

###############################################################################
def test_transport_policy_can_be_built_from_native_execution_settings() -> None:
    policy = LLMTransportPolicy.from_execution_settings(
        SimpleNamespace(
            native_model_call_seconds=7.5,
            model_max_attempts=3,
            retry_backoff_base_seconds=0.0,
            retry_backoff_max_seconds=0.0,
        )
    )

    assert policy.request_timeout_seconds == 7.5
    assert policy.stream_timeout_seconds == 7.5
    assert policy.max_attempts == 3
    assert policy.retry_delay(1) == 0.0

###############################################################################
def test_winerror_10013_is_safe_and_not_retryable() -> None:

    ###############################################################################
    class _PermissionDenied(OSError):
        winerror = 10013

    error = LLMProviderRequestError.from_exception(
        _PermissionDenied("provider secret should never be retained"),
        provider="opencode-go",
        model="deepseek-v4-flash",
        stage="chat",
    )

    assert error.retryable is False
    assert error.diagnostics["winerror"] == 10013
    assert "provider secret" not in str(error)
    assert "provider secret" not in safe_failure_detail(
        _PermissionDenied("provider secret should never be retained"),
        "Provider request failed.",
    )