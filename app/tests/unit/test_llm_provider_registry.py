from __future__ import annotations
from types import SimpleNamespace
import pytest
import json
import asyncio
from server.services.llm.factory import LLMFactory
from server.services.llm.errors import LLMConfigurationError, LLMProviderRequestError, LLMStructuredOutputError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.opencode_provider import OpenCodeProvider, OPENCODE_GO_PROVIDER, OPENCODE_PROVIDER
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.transport import LLMTransportPolicy
from server.services.llm.deepseek_provider import DeepSeekProvider
from pydantic import BaseModel
from server.services.llm.types import LLMRequest, LLMResult
from tests.conftest import run_async_in_thread
from server.domain.geospatial.providers import provider_execution_scope
from server.services.geospatial.provider_registry import ProviderExecutionPolicy, ProviderNotRegisteredError, ProviderRegistry
from server.services.geospatial.credential_resolver import GeospatialCredentialResolver
from server.services.geospatial.providers.base import ProviderAuthError, ProviderCircuitOpenError, ProviderRequest, ProviderRateLimitError, ProviderResponse, ProviderTimeoutError, ProviderUnavailableError

# --- test_llm_factory.py ---




###############################################################################
class _SettingsRepo:

    # -------------------------------------------------------------------------
    def get_required(self):  # noqa: ANN201
        return SimpleNamespace(
            ollama_url="http://localhost:11434",
            openai_base_url="https://api.openai.test",
            google_base_url="https://generativelanguage.googleapis.test",
            deepseek_base_url="https://api.deepseek.test",
        )

###############################################################################
class _CredentialsRepo:

    # -------------------------------------------------------------------------
    def __init__(self, mapping: dict[tuple[str, str], str]) -> None:
        self.mapping = mapping
        self.mark_used_calls: list[tuple[str, str]] = []

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        value = self.mapping.get((provider, label))
        if value is None:
            return None
        return SimpleNamespace(encrypted_value=value)

    # -------------------------------------------------------------------------
    def mark_used(self, *, provider: str, label: str) -> None:
        self.mark_used_calls.append((provider, label))

###############################################################################
class _Crypto:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        return f"decrypted:{encrypted_value}"

###############################################################################
class _FailingCrypto:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:  # noqa: ARG002
        raise ValueError("bad key")

###############################################################################
def test_openai_credential_is_read_from_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.services.llm.factory.OpenAIProvider",
        lambda *, api_key, base_url, **_kwargs: (api_key, base_url),
    )
    repo = _CredentialsRepo({("openai", "api_key"): "enc-openai"})
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=repo,
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("openai")
    assert provider == ("decrypted:enc-openai", "https://api.openai.test")
    assert repo.mark_used_calls == [("openai", "api_key")]

###############################################################################
def test_google_credential_is_read_from_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.services.llm.factory.GoogleProvider",
        lambda *, api_key, base_url, **_kwargs: (api_key, base_url),
    )
    repo = _CredentialsRepo({("google", "api_key"): "enc-google"})
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=repo,
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("google")
    assert provider == (
        "decrypted:enc-google",
        "https://generativelanguage.googleapis.test",
    )
    assert repo.mark_used_calls == [("google", "api_key")]

###############################################################################
def test_environment_variables_are_not_used_as_fallback(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-ignored")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-env-ignored")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-env-ignored")
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    with pytest.raises(ValueError, match="OpenAI credentials are not configured"):
        factory.get_provider("openai")
    with pytest.raises(ValueError, match="Google credentials are not configured"):
        factory.get_provider("google")

###############################################################################
def test_missing_credentials_follow_current_failure_path() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    with pytest.raises(ValueError, match="OpenAI credentials are not configured"):
        factory.get_provider("openai")

###############################################################################
def test_unreadable_credentials_raise_configuration_error() -> None:
    repo = _CredentialsRepo({("openai", "api_key"): "enc-openai"})
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=repo,
        crypto_service=_FailingCrypto(),
    )

    with pytest.raises(
        LLMConfigurationError,
        match="OpenAI credentials are saved but cannot be decrypted",
    ):
        factory.get_provider("openai")
    assert repo.mark_used_calls == []

###############################################################################
def test_get_provider_returns_ollama_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("ollama")
    assert isinstance(provider, OllamaProvider)

###############################################################################
def test_get_provider_returns_openai_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({("openai", "api_key"): "enc-openai"}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("openai")
    assert isinstance(provider, OpenAIProvider)

###############################################################################
def test_get_provider_returns_google_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({("google", "api_key"): "enc-google"}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("google")
    assert isinstance(provider, GoogleProvider)

###############################################################################
def test_get_provider_returns_opencode_provider_types() -> None:
    repo = _CredentialsRepo(
        {
            ("opencode", "api_key"): "enc-zen",
            ("opencode-go", "api_key"): "enc-go",
        }
    )
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=repo,
        crypto_service=_Crypto(),
    )

    zen = factory.get_provider("opencode")
    go = factory.get_provider("opencode-go")

    assert isinstance(zen, OpenCodeProvider)
    assert isinstance(go, OpenCodeProvider)
    assert zen.provider_name == "opencode"
    assert go.provider_name == "opencode-go"
    assert repo.mark_used_calls == [
        ("opencode", "api_key"),
        ("opencode-go", "api_key"),
    ]

###############################################################################
def test_all_canonical_providers_receive_one_shared_transport_policy() -> None:
    policy = LLMTransportPolicy(max_attempts=3, retry_backoff_base_seconds=0.0)
    repo = _CredentialsRepo(
        {
            ("openai", "api_key"): "enc-openai",
            ("google", "api_key"): "enc-google",
            ("deepseek", "api_key"): "enc-deepseek",
            ("opencode", "api_key"): "enc-zen",
            ("opencode-go", "api_key"): "enc-go",
        }
    )
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=repo,
        crypto_service=_Crypto(),
        transport_policy=policy,
    )

    providers = [
        factory.get_provider(provider)
        for provider in (
            "openai",
            "google",
            "deepseek",
            "opencode",
            "opencode-go",
            "ollama",
        )
    ]

    assert all(provider.transport_policy is policy for provider in providers)
    assert isinstance(providers[2], DeepSeekProvider)

###############################################################################
def test_missing_opencode_credentials_are_provider_specific() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    with pytest.raises(LLMConfigurationError, match="OpenCode Zen credentials"):
        factory.get_provider("opencode")
    with pytest.raises(LLMConfigurationError, match="OpenCode Go credentials"):
        factory.get_provider("opencode-go")

###############################################################################
def test_get_provider_keeps_structured_output_available_for_ollama() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )
    provider = factory.get_provider("ollama")

    assert isinstance(provider, OllamaProvider)

###############################################################################
@pytest.mark.parametrize(
    "provider",
    ["OpenAI", " openai", "openai ", "openai-compatible", "opencode_go"],
)
def test_get_provider_rejects_noncanonical_provider_ids(provider: str) -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    with pytest.raises(ValueError, match="Unsupported model provider"):
        factory.get_provider(provider)

# --- test_llm_providers.py ---




###############################################################################
class _StructuredPayload(BaseModel):
    answer: str = "structured"

###############################################################################
class _Message:

    # -------------------------------------------------------------------------
    def __init__(self, content) -> None:  # noqa: ANN001
        self.content = content
        self.response_metadata = {"provider": "fake"}
        self.usage_metadata = {"total_tokens": 3}
        self.additional_kwargs = {}

###############################################################################
class _StructuredModel:

    # -------------------------------------------------------------------------
    def __init__(self, schema: type[object]) -> None:
        self._schema = schema

    # -------------------------------------------------------------------------
    def invoke(self, _messages):  # noqa: ANN001, ANN202
        validator = getattr(self._schema, "model_validate", None)
        if callable(validator):
            return validator({"answer": "structured"})
        return {"answer": "structured"}

###############################################################################
class _FakeChatModel:
    instances: list["_FakeChatModel"] = []

    # -------------------------------------------------------------------------
    def __init__(self, **_kwargs) -> None:
        self.kwargs = _kwargs
        self.instances.append(self)

    # -------------------------------------------------------------------------
    def invoke(self, _messages):  # noqa: ANN001, ANN202
        return _Message("chat-ok")

    # -------------------------------------------------------------------------
    def stream(self, _messages):  # noqa: ANN001, ANN202
        yield _Message([{"text": "chunk-1"}])
        yield _Message("chunk-2")

    # -------------------------------------------------------------------------
    def with_structured_output(self, schema: type[object]) -> _StructuredModel:
        return _StructuredModel(schema)

###############################################################################
class _FakeEmbeddings:

    # -------------------------------------------------------------------------
    def __init__(self, **_kwargs) -> None:
        pass

    # -------------------------------------------------------------------------
    def embed_query(self, _input_text: str) -> list[float]:
        return [0.1, 0.2, 0.3]

###############################################################################
class _FakeOpenAIResponse:
    output_text = "chat-ok"

    # -------------------------------------------------------------------------
    def model_dump(
        self, *, mode: str, warnings: bool = False
    ) -> dict[str, object]:
        _ = warnings
        return {"mode": mode, "id": "resp-test"}

###############################################################################
class _FakeOpenAIResponses:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []
        self.parse_calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN001, ANN202
        self.create_calls.append(kwargs)
        if kwargs.get("stream"):
            return [
                SimpleNamespace(type="response.output_text.delta", delta="chunk-1"),
                SimpleNamespace(type="response.created", delta="ignored"),
                SimpleNamespace(type="response.output_text.delta", delta="chunk-2"),
                SimpleNamespace(
                    type="response.completed",
                    usage=SimpleNamespace(input_tokens=8, output_tokens=2),
                ),
            ]
        return _FakeOpenAIResponse()

    # -------------------------------------------------------------------------
    def parse(self, **kwargs):  # noqa: ANN001, ANN202
        self.parse_calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=_StructuredPayload(answer="structured"),
            output_text="",
        )

###############################################################################
class _FakeOpenAIEmbeddingEndpoint:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.create_calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def create(self, **kwargs):  # noqa: ANN001, ANN202
        self.create_calls.append(kwargs)
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])])

###############################################################################
class _FakeOpenAIClient:
    instances: list["_FakeOpenAIClient"] = []

    # -------------------------------------------------------------------------
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.responses = _FakeOpenAIResponses()
        self.embeddings = _FakeOpenAIEmbeddingEndpoint()
        self.instances.append(self)

###############################################################################
class _FakeGoogleModels:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.generate_content_calls: list[dict[str, object]] = []
        self.generate_content_stream_calls: list[dict[str, object]] = []
        self.embed_content_calls: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    def generate_content(self, **kwargs):  # noqa: ANN001, ANN202
        self.generate_content_calls.append(kwargs)
        config = kwargs.get("config")
        if isinstance(config, dict) and config.get("response_mime_type"):
            return SimpleNamespace(text=json.dumps({"answer": "structured"}))
        return SimpleNamespace(
            text="chat-ok",
            model_dump=lambda *, mode, warnings=False: {"mode": mode},
        )

    # -------------------------------------------------------------------------
    def generate_content_stream(self, **kwargs):  # noqa: ANN001, ANN202
        self.generate_content_stream_calls.append(kwargs)
        return [
            SimpleNamespace(text="chunk-1"),
            SimpleNamespace(text="chunk-2"),
            SimpleNamespace(
                text="",
                usage_metadata=SimpleNamespace(
                    prompt_token_count=8,
                    candidates_token_count=2,
                ),
            ),
        ]

    # -------------------------------------------------------------------------
    def embed_content(self, **kwargs):  # noqa: ANN001, ANN202
        self.embed_content_calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=[0.1, 0.2, 0.3])])

###############################################################################
class _FakeGoogleClient:
    instances: list["_FakeGoogleClient"] = []

    # -------------------------------------------------------------------------
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.models = _FakeGoogleModels()
        self.instances.append(self)

###############################################################################
class _FakeHttpOptions:

    # -------------------------------------------------------------------------
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

###############################################################################
def _request() -> LLMRequest:
    return LLMRequest(
        model="test-model",
        messages=[
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ],
    )

###############################################################################
def test_openai_provider_uses_responses_api(monkeypatch) -> None:
    _FakeOpenAIClient.instances = []
    monkeypatch.setattr("server.services.llm.openai_provider.OpenAI", _FakeOpenAIClient)
    provider = OpenAIProvider(api_key="k", base_url="https://api.openai.test/v1")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    stream = provider.stream_chat(_request())
    assert list(stream) == ["chunk-1", "chunk-2"]
    assert stream.context_usage is not None
    assert stream.context_usage["reported_input_tokens"] == 8
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]

    first_client = _FakeOpenAIClient.instances[0]
    assert first_client.kwargs["api_key"] == "k"
    assert first_client.kwargs["base_url"] == "https://api.openai.test/v1"
    assert first_client.kwargs["timeout"] == 30.0
    assert first_client.kwargs["max_retries"] == 0
    assert first_client.kwargs["http_client"].trust_env is False
    assert first_client.responses.create_calls[0]["model"] == "test-model"
    assert first_client.responses.create_calls[0]["input"] == _request().messages
    assert (
        _FakeOpenAIClient.instances[2].responses.parse_calls[0]["text_format"]
        is _StructuredPayload
    )
    assert _FakeOpenAIClient.instances[3].embeddings.create_calls[0] == {
        "model": "embed-model",
        "input": "hello",
    }

###############################################################################
def test_openai_reasoning_catalog_policy_omits_temperature_and_caps_output(
    monkeypatch,
) -> None:
    _FakeOpenAIClient.instances = []
    monkeypatch.setattr("server.services.llm.openai_provider.OpenAI", _FakeOpenAIClient)
    provider = OpenAIProvider(api_key="k")
    request = LLMRequest(
        model="gpt-5.2",
        messages=[{"role": "user", "content": "Extract"}],
        temperature=0.9,
        metadata={"max_tokens": 200_000},
    )

    provider.chat(request)
    provider.structured_output(request, schema=_StructuredPayload)

    client = _FakeOpenAIClient.instances[0]
    chat_call = client.responses.create_calls[0]
    parse_call = _FakeOpenAIClient.instances[1].responses.parse_calls[0]
    assert "temperature" not in chat_call
    assert chat_call["max_output_tokens"] == 128_000
    assert "temperature" not in parse_call
    assert parse_call["max_output_tokens"] == 128_000

###############################################################################
def test_openai_structured_output_rejects_unsupported_model_before_api_call(
    monkeypatch,
) -> None:
    _FakeOpenAIClient.instances = []
    monkeypatch.setattr("server.services.llm.openai_provider.OpenAI", _FakeOpenAIClient)
    provider = OpenAIProvider(api_key="k")

    provider.list_models = lambda: [
        SimpleNamespace(provider="openai", name="chat-only", capabilities=["chat"])
    ]

    request = LLMRequest(model="chat-only", messages=_request().messages)
    try:
        provider.structured_output(request, schema=_StructuredPayload)
    except LLMStructuredOutputError as exc:
        assert exc.category == "model_capability"
        assert "does not support structured output" in str(exc)
    else:
        raise AssertionError("structured_output should reject unsupported models")

    assert _FakeOpenAIClient.instances == []

###############################################################################
def test_google_provider_uses_genai_sdk(monkeypatch) -> None:
    _FakeGoogleClient.instances = []
    monkeypatch.setattr(
        "server.services.llm.google_provider.genai.Client", _FakeGoogleClient
    )
    monkeypatch.setattr(
        "server.services.llm.google_provider.genai_types.HttpOptions",
        _FakeHttpOptions,
    )
    provider = GoogleProvider(api_key="k", base_url="https://google.example/v1beta")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    stream = provider.stream_chat(_request())
    assert list(stream) == ["chunk-1", "chunk-2"]
    assert stream.context_usage is not None
    assert stream.context_usage["reported_input_tokens"] == 8
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]

    first_client = _FakeGoogleClient.instances[0]
    assert first_client.kwargs["api_key"] == "k"
    http_options = first_client.kwargs["http_options"].kwargs
    assert http_options["baseUrl"] == "https://google.example/v1beta"
    assert http_options["apiVersion"] == "v1beta"
    assert http_options["timeout"] == 30_000
    assert http_options["retryOptions"].attempts == 1
    assert http_options["clientArgs"]["trust_env"] is False
    chat_call = first_client.models.generate_content_calls[0]
    assert chat_call["model"] == "test-model"
    assert chat_call["contents"] == [
        {"role": "user", "parts": [{"text": "Hello"}]},
    ]
    assert chat_call["config"] == {
        "temperature": 0.2,
        "system_instruction": "System prompt",
    }
    structured_call = _FakeGoogleClient.instances[2].models.generate_content_calls[0]
    assert structured_call["config"]["response_mime_type"] == "application/json"
    assert "response_json_schema" in structured_call["config"]
    assert _FakeGoogleClient.instances[3].models.embed_content_calls[0] == {
        "model": "embed-model",
        "contents": "hello",
    }

###############################################################################
def test_ollama_provider_http_paths(monkeypatch) -> None:
    post_calls: list[tuple[str, dict[str, object]]] = []
    stream_calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(self, path, payload):  # noqa: ANN001
        post_calls.append((path, payload))
        if path == "/api/embeddings":
            return {"embedding": [0.1, 0.2, 0.3]}
        if payload.get("format"):
            return {"message": {"content": json.dumps({"answer": "structured"})}}
        return {"message": {"content": "chat-ok"}, "done_reason": "stop"}

    def fake_stream(self, path, payload):  # noqa: ANN001
        stream_calls.append((path, payload))
        return iter(
            [
                {"message": {"content": "chunk-1"}},
                {
                    "message": {"content": "chunk-2"},
                    "done": True,
                    "prompt_eval_count": 8,
                    "eval_count": 2,
                },
            ]
        )

    monkeypatch.setattr(OllamaProvider, "_post_json", fake_post)
    monkeypatch.setattr(OllamaProvider, "_stream_post", fake_stream)
    provider = OllamaProvider(base_url="http://localhost:11434")

    response = provider.chat(_request())
    assert isinstance(response, LLMResult)
    assert response.content == "chat-ok"
    stream = provider.stream_chat(_request())
    assert list(stream) == ["chunk-1", "chunk-2"]
    assert stream.context_usage is not None
    assert stream.context_usage["reported_input_tokens"] == 8
    assert provider.structured_output(_request(), schema=_StructuredPayload) == {
        "answer": "structured"
    }
    assert provider.embeddings(model="embed-model", input_text="hello") == [
        0.1,
        0.2,
        0.3,
    ]
    assert post_calls[0][0] == "/api/show"
    chat_payload = next(payload for path, payload in post_calls if path == "/api/chat")
    assert stream_calls[0][0] == "/api/chat"
    assert "num_ctx" not in chat_payload.get("options", {})
    structured_payload = next(
        payload for _, payload in post_calls if payload.get("format")
    )
    assert "think" not in structured_payload
    assert response.context_usage is not None
    assert response.context_usage["provider"] == "ollama"

###############################################################################
def test_ollama_thinking_control_uses_exact_show_metadata(monkeypatch) -> None:
    payloads: list[dict[str, object]] = []

    def fake_post(self, path, payload):  # noqa: ANN001
        if path == "/api/show":
            if payload["name"] == "gpt-oss-local":
                return {"details": {"family": "gpt-oss"}}
            return {"details": {"family": "qwen3"}, "capabilities": ["thinking"]}
        payloads.append(payload)
        return {"message": {"content": json.dumps({"answer": "ok"})}}

    monkeypatch.setattr(OllamaProvider, "_post_json", fake_post)
    provider = OllamaProvider(base_url="http://localhost:11434")

    provider.structured_output(
        LLMRequest(model="gpt-oss-local", messages=[{"role": "user", "content": "x"}]),
        schema=_StructuredPayload,
    )
    provider.structured_output(
        LLMRequest(model="qwen-local", messages=[{"role": "user", "content": "x"}]),
        schema=_StructuredPayload,
    )

    structured_payloads = [payload for payload in payloads if payload.get("format")]
    assert structured_payloads[0]["think"] == "low"
    assert structured_payloads[1]["think"] is False

###############################################################################
def test_all_llm_adapters_normalize_transport_setup_timeouts(monkeypatch) -> None:
    providers = [
        OpenAIProvider(api_key="secret"),
        GoogleProvider(api_key="secret"),
        DeepSeekProvider(api_key="secret"),
        OpenCodeProvider(api_key="secret", provider_name=OPENCODE_PROVIDER),
        OpenCodeProvider(api_key="secret", provider_name=OPENCODE_GO_PROVIDER),
        OllamaProvider(base_url="http://ollama.test"),
    ]

    def fail(*_args, **_kwargs):  # noqa: ANN002, ANN003
        raise TimeoutError("provider transport setup timed out")

    for provider in providers:
        request = LLMRequest(
            model=(
                "deepseek-v4-flash"
                if provider.provider_name in {"deepseek", "opencode", "opencode-go"}
                else "test-model"
            ),
            messages=[{"role": "user", "content": "hello"}],
            provider_session_id="conversation-test",
        )
        if isinstance(provider, OllamaProvider):
            monkeypatch.setattr(provider, "_post_json_for_request", fail)
        else:
            monkeypatch.setattr(provider, "_client_for_request", fail)

        with pytest.raises(LLMProviderRequestError) as error:
            provider.chat(request)

        assert error.value.provider == provider.provider_name
        assert error.value.code == "provider_timeout"
        assert error.value.timeout_origin == "provider_transport"

# --- test_provider_registry.py ---



###############################################################################
class _Provider:
    provider_id = "example"

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"ok": True},
        )


###############################################################################
class _LayerProvider:
    provider_id = "gibs"

    # -------------------------------------------------------------------------
    async def list_layers(
        self,
        *,
        query: str | None = None,
        limit: int = 100,
        refresh: bool = False,
    ) -> list[object]:
        del query, limit, refresh
        return []

###############################################################################
class _TimeoutProvider:
    provider_id = "slow"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        await asyncio.sleep(1.0)
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"ok": True},
        )

###############################################################################
class _FlakyProvider:
    provider_id = "flaky"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            raise ProviderUnavailableError("temporary outage")
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"attempts": self.calls},
        )

###############################################################################
class _AuthProvider:
    provider_id = "auth"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        raise ProviderAuthError("missing key")

###############################################################################
class _RateLimitedProvider:
    provider_id = "rate-limited"

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.calls = 0

    # -------------------------------------------------------------------------
    async def fetch(self, request: ProviderRequest) -> ProviderResponse:
        self.calls += 1
        if self.calls == 1:
            raise ProviderRateLimitError(
                "slow down", retry_after_seconds=0.0
            )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={"attempts": self.calls},
        )

###############################################################################
class _SavedCredentialRepository:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.mark_used_calls: list[tuple[str, str]] = []

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        if provider == "tomtom" and label == "api_key":
            return SimpleNamespace(encrypted_value="encrypted-tomtom-key")
        return None

    # -------------------------------------------------------------------------
    def mark_used(self, *, provider: str, label: str) -> None:
        self.mark_used_calls.append((provider, label))

###############################################################################
class _CredentialDecryptor:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        assert encrypted_value == "encrypted-tomtom-key"
        return "database-only-tomtom-key"

###############################################################################
def test_provider_registry_registers_and_fetches_provider() -> None:
    registry = ProviderRegistry(providers=[_Provider()])

    response = run_async_in_thread(
        registry.fetch("example", ProviderRequest(capability_id="capability"))
    )

    assert registry.list_provider_ids() == ["example"]
    assert response.payload == {"ok": True}

###############################################################################
def test_provider_registry_errors_for_missing_provider() -> None:
    registry = ProviderRegistry()

    try:
        registry.get("missing")
    except ProviderNotRegisteredError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Missing provider unexpectedly resolved.")

###############################################################################
def test_provider_registry_uses_canonical_gibs_id_only() -> None:
    registry = ProviderRegistry(providers=[_LayerProvider()])

    layers = run_async_in_thread(
        registry.list_layers("gibs", query="SRTM", limit=20, refresh=False)
    )

    assert layers == []
    try:
        run_async_in_thread(
            registry.list_layers("nasa_gibs", query="SRTM", limit=20, refresh=False)
        )
    except ProviderNotRegisteredError as exc:
        assert "nasa_gibs" in str(exc)
    else:
        raise AssertionError("Retired NASA GIBS provider alias unexpectedly resolved.")

###############################################################################
def test_provider_registry_builds_manifest_backed_providers() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "gibs" in registry.list_provider_ids()
    assert "mapillary" not in registry.list_provider_ids()
    assert "rainviewer" in registry.list_provider_ids()
    assert "fallback" not in registry.list_provider_ids()
    assert "osm" not in registry.list_provider_ids()
    assert "gibs" in registry.list_provider_ids()

###############################################################################
def test_provider_registry_rejects_provider_entries_without_canonical_provider_id() -> None:

    ###############################################################################
    class _Loader:

        # -------------------------------------------------------------------------
        def load_all(self) -> dict[str, list[dict[str, object]]]:
            return {
                "providers": [{"id": "gibs", "name": "GIBS"}],
                "basemaps": [],
                "overlays": [],
                "cameras": [],
                "transit": [],
                "tools": [],
                "runtime_profiles": [],
            }

    registry = ProviderRegistry(manifest_loader=_Loader())  # type: ignore[arg-type]

    registry.build_from_manifests()

    assert "gibs" not in registry.list_provider_ids()

###############################################################################
def test_provider_registry_passes_database_only_credentials_to_provider() -> None:
    repository = _SavedCredentialRepository()
    resolver = GeospatialCredentialResolver(
        credentials_repo=repository,  # type: ignore[arg-type]
        crypto_service=_CredentialDecryptor(),
    )
    registry = ProviderRegistry(credential_resolver=resolver)

    registry.build_from_manifests()

    provider = registry.get("tomtom")
    assert getattr(provider, "api_key") == "database-only-tomtom-key"
    assert repository.mark_used_calls == [("tomtom", "api_key")]

###############################################################################
def test_provider_registry_skips_basemap_and_metadata_only_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "osm_tiles" not in registry.list_provider_ids()

###############################################################################
def test_provider_registry_raises_for_unknown_fetchable_provider() -> None:

    ###############################################################################
    class _Loader:

        # -------------------------------------------------------------------------
        def load_all(self) -> dict[str, list[dict[str, object]]]:
            return {
                "providers": [],
                "basemaps": [],
                "overlays": [
                    {
                        "id": "custom_overlay",
                        "provider": "unknown_provider",
                        "capabilityKind": "raster-overlay",
                    }
                ],
                "cameras": [],
                "transit": [],
                "tools": [],
                "runtime_profiles": [],
            }

    registry = ProviderRegistry(manifest_loader=_Loader())  # type: ignore[arg-type]

    try:
        registry.build_from_manifests()
    except ProviderNotRegisteredError as exc:
        assert "unknown_provider" in str(exc)
    else:
        raise AssertionError("Unknown fetchable provider unexpectedly registered.")

###############################################################################
def test_provider_registry_times_out_slow_provider() -> None:
    registry = ProviderRegistry(
        providers=[_TimeoutProvider()],
        execution_policy=ProviderExecutionPolicy(timeout_seconds=0.01),
    )

    try:
        run_async_in_thread(
            registry.fetch("slow", ProviderRequest(capability_id="slow_layer"))
        )
    except ProviderTimeoutError as exc:
        assert "slow" in str(exc)
    else:
        raise AssertionError("Slow provider unexpectedly succeeded.")

###############################################################################
def test_provider_registry_retries_transient_provider_failure() -> None:
    provider = _FlakyProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(max_attempts=2),
    )

    response = run_async_in_thread(
        registry.fetch("flaky", ProviderRequest(capability_id="flaky_layer"))
    )

    assert response.payload == {"attempts": 2}

###############################################################################
def test_provider_registry_does_not_retry_after_deadline_expires() -> None:
    provider = _TimeoutProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(
            timeout_seconds=0.01,
            max_attempts=2,
            retry_backoff_base_seconds=0.0,
            retry_backoff_max_seconds=0.0,
        ),
    )

    try:
        run_async_in_thread(
            registry.fetch("slow", ProviderRequest(capability_id="slow_layer"))
        )
    except ProviderTimeoutError:
        pass
    else:
        raise AssertionError("Slow provider unexpectedly succeeded.")
    assert provider.calls == 1

###############################################################################
def test_provider_registry_preserves_provider_specific_timeout_floor() -> None:
    registry = ProviderRegistry(
        providers=[_TimeoutProvider()],
        execution_policy=ProviderExecutionPolicy(
            timeout_seconds=0.01,
            provider_timeout_seconds={"slow": 0.05},
        ),
    )

    assert registry._timeout_seconds("slow") == 0.05  # pyright: ignore[reportPrivateUsage]
    assert registry._timeout_seconds("other") == 0.01  # pyright: ignore[reportPrivateUsage]

    # An agent run scopes a generic policy; the provider floor must survive it.
    with provider_execution_scope(ProviderExecutionPolicy(timeout_seconds=0.02)):
        assert registry._timeout_seconds("slow") == 0.05  # pyright: ignore[reportPrivateUsage]
        assert registry._timeout_seconds("other") == 0.02  # pyright: ignore[reportPrivateUsage]

###############################################################################
def test_provider_registry_retries_bounded_rate_limit_after_retry_after() -> None:
    provider = _RateLimitedProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(
            max_attempts=2,
            retry_backoff_base_seconds=0.0,
            retry_backoff_max_seconds=0.0,
        ),
    )

    response = run_async_in_thread(
        registry.fetch("rate-limited", ProviderRequest(capability_id="limited"))
    )

    assert response.payload == {"attempts": 2}

###############################################################################
def test_provider_registry_does_not_retry_auth_errors() -> None:
    provider = _AuthProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(max_attempts=3),
    )

    try:
        run_async_in_thread(
            registry.fetch("auth", ProviderRequest(capability_id="secure"))
        )
    except ProviderAuthError:
        pass
    else:
        raise AssertionError("Auth provider unexpectedly succeeded.")
    assert provider.calls == 1

###############################################################################
def test_provider_registry_opens_circuit_after_repeated_failures() -> None:
    registry = ProviderRegistry(
        providers=[_TimeoutProvider()],
        execution_policy=ProviderExecutionPolicy(
            timeout_seconds=0.01,
            circuit_breaker_failures=1,
        ),
    )

    try:
        run_async_in_thread(
            registry.fetch("slow", ProviderRequest(capability_id="slow_layer"))
        )
    except ProviderTimeoutError:
        pass
    else:
        raise AssertionError("Slow provider unexpectedly succeeded.")

    try:
        run_async_in_thread(
            registry.fetch("slow", ProviderRequest(capability_id="slow_layer"))
        )
    except ProviderCircuitOpenError:
        pass
    else:
        raise AssertionError("Open circuit did not reject the provider.")

###############################################################################
def test_provider_registry_recovers_circuit_after_recovery_window() -> None:
    provider = _FlakyProvider()
    registry = ProviderRegistry(
        providers=[provider],
        execution_policy=ProviderExecutionPolicy(
            max_attempts=1,
            circuit_breaker_failures=1,
            circuit_recovery_seconds=0,
        ),
    )

    try:
        run_async_in_thread(
            registry.fetch("flaky", ProviderRequest(capability_id="flaky_layer"))
        )
    except ProviderUnavailableError:
        pass
    else:
        raise AssertionError("Flaky provider unexpectedly succeeded on first call.")

    response = run_async_in_thread(
        registry.fetch("flaky", ProviderRequest(capability_id="flaky_layer"))
    )

    assert response.payload == {"attempts": 2}