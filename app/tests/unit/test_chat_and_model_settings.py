from __future__ import annotations
from pydantic import ValidationError
from server.contracts.chat import ModelSettingsUpdateRequest, OllamaPullRequest, OllamaPullResponse, OllamaRefreshResponse
from server.services.chat.maintenance_service import ChatMaintenanceService
from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from types import SimpleNamespace
from server.services.chat.settings_service import ChatSettingsService
from server.repositories.model_settings import ModelSettingsRepository
import pytest
from typing import Any
from unittest.mock import Mock, call
from tests.e2e.helpers.model_capability_metadata import selected_model_tool_support_metadata
from server.prompts.context import build_compacted_history_summary
from server.services.llm.errors import LLMContextLimitError
from server.services.llm.context_budget import RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY, apply_reported_usage, calculate_context_usage_percent, compute_context_usage, compute_ollama_context_usage, estimate_message_tokens, merge_provider_context_usage, normalize_model_context_profile, prepare_request, profile_to_request_metadata, resolve_model_context_profile
from server.services.llm.types import LLMRequest, LLMToolDefinition, ModelContextProfile

# --- test_chat_domain_contract.py ---



###############################################################################
def test_model_settings_update_request_forbids_unknown_fields() -> None:
    try:
        ModelSettingsUpdateRequest(unknown_field="x")
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError for unknown field")

###############################################################################
def test_model_settings_update_request_requires_string_credentials() -> None:
    try:
        ModelSettingsUpdateRequest(credentials={"openai": {"api_key": 123}})
    except ValidationError:
        pass
    else:
        raise AssertionError("Expected ValidationError for non-string credential value")

###############################################################################
def test_model_settings_update_request_accepts_valid_payload() -> None:
    payload = ModelSettingsUpdateRequest(
        active_provider_mode="cloud",
        agent_model_provider="openai",
        agent_model_name="gpt-4.1-mini",
        credentials={"openai": {"api_key": "secret"}},
    )

    assert payload.active_provider_mode == "cloud"
    assert payload.agent_model_provider == "openai"
    assert payload.credentials["openai"]["api_key"] == "secret"

###############################################################################
def test_model_settings_update_request_rejects_invalid_base_urls() -> None:
    try:
        ModelSettingsUpdateRequest(ollama_url="not-a-url")
    except ValidationError as exc:
        assert "Base URL must start with http:// or https://" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid Ollama URL")

# --- test_chat_maintenance_service.py ---


###############################################################################
class _UnusedProviderFactory:

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ANN201
        raise AssertionError(f"Unexpected provider lookup: {provider}")

###############################################################################
def test_maintenance_service_delegates_to_ollama_provider() -> None:
    provider_calls: list[tuple[str, str | None]] = []

    ###############################################################################
    class _Provider:

        # -------------------------------------------------------------------------
        def __init__(self, *, base_url: str) -> None:
            provider_calls.append(("init", base_url))

        # -------------------------------------------------------------------------
        def list_library_models(self):  # noqa: ANN201
            provider_calls.append(("list_library_models", None))
            return [type("Model", (), {"name": "llama3.2"})()]

        # -------------------------------------------------------------------------
        def list_models(self):  # noqa: ANN201
            provider_calls.append(("list_models", None))
            return [
                type(
                    "Model",
                    (),
                    {
                        "name": "llama3.2",
                        "description": "local",
                        "provider": "ollama",
                        "capabilities": ["chat", "structured_output", "tools"],
                        "metadata": {"tool_support_source": "ollama_show"},
                    },
                )()
            ]

        # -------------------------------------------------------------------------
        def pull_model(self, *, model: str):  # noqa: ANN201
            provider_calls.append(("pull_model", model))
            return {"status": "ok", "model": model}

        # -------------------------------------------------------------------------
        def health_check(self):  # noqa: ANN201
            provider_calls.append(("health_check", None))
            return {"ok": True, "detail": "healthy"}

    service = ChatMaintenanceService(
        get_ollama_url=lambda: "http://localhost:11434",
        model_library_service=ChatModelLibraryService(
            provider_factory=_UnusedProviderFactory()
        ),
        ollama_tool_capability_cache=OllamaToolCapabilityCache(),
        ollama_provider_factory=lambda base_url, _cache: _Provider(base_url=base_url),
    )

    refresh = service.refresh_ollama_models()
    pull = service.pull_ollama_model(OllamaPullRequest(model="llama3.2"))
    health = service.get_ollama_health()

    assert isinstance(refresh, OllamaRefreshResponse)
    assert refresh.local_model_capabilities[0].supports_tools is True
    assert refresh.local_model_capabilities[0].supports_structured_output is True
    assert refresh.local_model_capabilities[0].tool_support_source == "ollama_show"
    assert isinstance(pull, OllamaPullResponse)
    assert health.ok is True
    assert ("pull_model", "llama3.2") in provider_calls

###############################################################################
def test_maintenance_service_does_not_report_catalog_failure_as_success() -> None:

    ###############################################################################
    class _UnavailableProvider:
        last_list_library_models_error = "ollama unavailable"
        last_list_models_error = "ollama unavailable"

        # -------------------------------------------------------------------------
        def list_library_models(self):  # noqa: ANN201
            return []

        # -------------------------------------------------------------------------
        def list_models(self):  # noqa: ANN201
            return []

    service = ChatMaintenanceService(
        get_ollama_url=lambda: "http://localhost:11434",
        model_library_service=ChatModelLibraryService(
            provider_factory=_UnusedProviderFactory()
        ),
        ollama_tool_capability_cache=OllamaToolCapabilityCache(),
        ollama_provider_factory=lambda _base_url, _cache: _UnavailableProvider(),
    )

    refresh = service.refresh_ollama_models()

    assert refresh.status == "unavailable"
    assert refresh.stale is True
    assert "ollama unavailable" in (refresh.message or "")

# --- test_chat_settings_service.py ---



###############################################################################
class _SettingsRepo:

    # -------------------------------------------------------------------------
    def get_required(self):  # noqa: ANN201
        return SimpleNamespace(
            active_provider_mode="cloud",
            agent_model_provider="openai",
            agent_model_name="gpt-4.1-mini",
            ollama_url="http://localhost:11434",
            openai_base_url=None,
            google_base_url=None,
            deepseek_base_url=None,
        )

###############################################################################
class _CredentialsRepo:

    # -------------------------------------------------------------------------
    def list_active(self):  # noqa: ANN201
        return [
            SimpleNamespace(
                provider="openai",
                label="api_key",
                encrypted_value="readable",
            ),
            SimpleNamespace(
                provider="google",
                label="api_key",
                encrypted_value="broken",
            ),
        ]

###############################################################################
class _Crypto:

    # -------------------------------------------------------------------------
    def decrypt(self, encrypted_value: str) -> str:
        if encrypted_value == "broken":
            raise ValueError("bad key")
        return "secret"

###############################################################################
def test_settings_response_reports_credential_health() -> None:
    service = ChatSettingsService(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo(),
        crypto_service=_Crypto(),
        model_library_service=SimpleNamespace(
            normalize_ollama_url=lambda value: value,
        ),
    )

    response = service.get_settings()

    assert response.credentials == {
        "openai": {"api_key": True},
        "google": {"api_key": True},
    }
    assert response.credential_health == {
        "openai": {"api_key": "healthy"},
        "google": {"api_key": "unreadable"},
    }

# --- test_llm_settings_repository.py ---


###############################################################################
def test_model_settings_repository_creates_and_updates_record(sqlite_backend) -> None:
    repository = ModelSettingsRepository(sqlite_backend)
    repository.seed_required()
    current = repository.get_required()
    assert current.id is not None
    updated = repository.update(
        active_provider_mode="cloud",
        agent_model_provider="google",
        agent_model_name="gemini-2.0-flash",
        ollama_url="http://localhost:11434",
        openai_base_url="https://api.openai.com/v1",
        google_base_url="https://generativelanguage.googleapis.com/v1beta",
        deepseek_base_url="https://api.deepseek.com",
    )
    assert updated.active_provider_mode == "cloud"
    assert updated.agent_model_provider == "google"
    assert updated.agent_model_name == "gemini-2.0-flash"

# --- test_model_settings_repository.py ---



###############################################################################
def test_get_required_fails_when_initialization_has_not_seeded_settings(
    sqlite_backend,
) -> None:
    repo = ModelSettingsRepository(sqlite_backend)

    with pytest.raises(RuntimeError, match="database initialization must seed it"):
        repo.get_required()

###############################################################################
def test_seed_required_creates_singleton_and_is_idempotent(sqlite_backend) -> None:
    repo = ModelSettingsRepository(sqlite_backend)

    repo.seed_required()
    repo.seed_required()
    current = repo.get_required()

    assert current.id is not None
    assert current.active_provider_mode == "cloud"
    assert current.agent_model_provider == ""
    assert current.agent_model_name == ""

###############################################################################
def test_update_persists_selected_agent_model(sqlite_backend) -> None:
    repo = ModelSettingsRepository(sqlite_backend)
    repo.seed_required()

    repo.update(
        active_provider_mode="local",
        agent_model_provider="ollama",
        agent_model_name="llama3.2",
        ollama_url="http://localhost:11434",
        openai_base_url=None,
        google_base_url=None,
        deepseek_base_url=None,
    )
    current = repo.get_required()

    assert current.agent_model_provider == "ollama"
    assert current.agent_model_name == "llama3.2"

# --- test_model_capability_metadata_helper.py ---





###############################################################################
class _Response:

    # -------------------------------------------------------------------------
    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    # -------------------------------------------------------------------------
    def json(self) -> dict[str, Any]:
        return self._payload


###############################################################################
@pytest.mark.parametrize(
    ("supports_tools", "expected_ready", "expected_reason"),
    [
        (True, True, ""),
        (False, False, "Selected model metadata reports no tool-calling support."),
        (
            None,
            False,
            "Selected model tool-calling support is not verified by metadata.",
        ),
    ],
)
def test_selected_model_tool_support_uses_metadata_without_inference(
    supports_tools: bool | None,
    expected_ready: bool,
    expected_reason: str,
) -> None:
    request = Mock()
    request.get.side_effect = [
        _Response(
            200,
            {
                "agent_model_provider": "opencode-go",
                "agent_model_name": "beam-free",
            },
        ),
        _Response(
            200,
            {
                "cloud": [
                    {
                        "provider": "opencode-go",
                        "name": "beam-free",
                        "supports_tools": supports_tools,
                        "tool_support_source": "provider_protocol_registry",
                        "protocol": "openai-chat-completions",
                    }
                ],
                "local": [],
            },
        ),
    ]
    page = Mock(request=request)

    ready, reason, evidence = selected_model_tool_support_metadata(
        page, "http://127.0.0.1:8000/"
    )

    assert ready is expected_ready
    assert reason == expected_reason
    assert evidence["provider"] == "opencode-go"
    assert evidence["model"] == "beam-free"
    assert evidence["supports_tools"] is supports_tools
    assert request.get.call_args_list == [
        call("http://127.0.0.1:8000/api/chat/settings", timeout=10_000),
        call("http://127.0.0.1:8000/api/chat/models", timeout=10_000),
    ]
    request.post.assert_not_called()

# --- test_context_budget.py ---



###############################################################################
def _request(
    content: str,
    *,
    model: str = "unknown-local-model",
    metadata: dict[str, object] | None = None,
) -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[
            {"role": "system", "content": "You are concise."},
            {"role": "user", "content": content},
        ],
        metadata=dict(metadata or {}),
    )

###############################################################################
def test_static_catalog_profile_is_exact_and_provider_scoped() -> None:
    usage = compute_context_usage(
        _request(
            "hello",
            model="gpt-5-mini",
            metadata={"max_tokens": 1024},
        ),
        provider="openai",
    )

    assert usage.selected_context_window == 400_000
    assert usage.model_context_limit == 400_000
    # Known models are still bounded by the application working-set ceiling,
    # even when the provider advertises a much larger context window.
    assert usage.usable_prompt_budget_tokens == 62_464
    assert usage.context_profile_source == "openai_model_catalog"
    assert usage.provider == "openai"
    assert usage.peak_request_tokens == usage.estimated_input_tokens
    assert usage.total_input_tokens == usage.estimated_input_tokens

###############################################################################
def test_model_name_alone_never_creates_a_local_context_cap() -> None:
    assert resolve_model_context_profile("ollama", "qwen3.5:2b") is None

    usage = compute_ollama_context_usage(_request("hello", model="qwen3.5:2b"))
    assert usage.selected_context_window is None
    assert usage.usage_percent is None
    assert usage.usage_source == "estimated"
    assert usage.estimated_input_tokens > 0

###############################################################################
def test_provider_metadata_supplies_the_local_cap_and_schema_reservation() -> None:
    usage = compute_ollama_context_usage(
        _request(
            "x" * 5000,
            model="local-alias",
            metadata={
                "context_window_tokens": 40_960,
                "maximum_output_tokens": 4096,
                "context_profile_source": "ollama_show_model_info",
            },
        ),
        response_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
    )

    assert usage.selected_context_window == 40_960
    assert usage.response_schema_tokens > 0
    assert usage.reserved_output_tokens == 4096
    assert usage.context_profile_source == "ollama_show_model_info"
    assert usage.usable_prompt_budget_tokens == 36_352

###############################################################################
@pytest.mark.parametrize("value", [True, False, 0, -1, 1.5, "not-a-number"])
def test_context_profile_normalizer_rejects_malformed_token_counts(value: object) -> None:
    assert (
        normalize_model_context_profile(
            "ollama",
            "local-alias",
            metadata={
                "context_window_tokens": value,
                "context_profile_source": "ollama_show_model_info",
            },
        )
        is None
    )

###############################################################################
def test_context_profile_normalizer_rejects_conflicting_aliases_and_preserves_authority() -> None:
    assert (
        normalize_model_context_profile(
            "opencode",
            "runtime-model",
            metadata={
                "context_window_tokens": 8192,
                "context_length": 16_384,
                "context_profile_source": "provider_models_api",
                "context_metadata_authority": "provider",
            },
        )
        is None
    )

    profile = normalize_model_context_profile(
        "opencode",
        "runtime-model",
        metadata={
            "context_window": 8192,
            "max_output_tokens": 512,
            "context_profile_source": "provider_models_api",
            "context_metadata_authority": "provider",
        },
    )

    assert profile is not None
    assert profile.context_window_tokens == 8192
    assert profile.maximum_output_tokens == 512
    assert profile.metadata_authority == "provider"
    assert profile_to_request_metadata(profile)["context_profile_model"] == "runtime-model"

###############################################################################
def test_provider_usage_cannot_erase_canonical_model_limit() -> None:
    profile = ModelContextProfile(
        provider="ollama",
        model="local-alias",
        context_window_tokens=40_960,
        maximum_output_tokens=4096,
        default_output_reserve=4096,
        metadata_source="ollama_show_model_info",
        metadata_authority="provider",
    )
    usage = compute_context_usage(
        _request(
            "hello",
            model="local-alias",
            metadata=profile_to_request_metadata(profile),
        ),
        provider="ollama",
    )

    merged = merge_provider_context_usage(
        usage,
        {"reported_input_tokens": 640, "reported_output_tokens": 32},
    )

    assert merged.model_context_limit == 40_960
    assert merged.selected_context_window == 40_960
    assert merged.reported_input_tokens == 640
    assert merged.reported_output_tokens == 32

###############################################################################
def test_complete_request_counts_messages_tools_and_response_schema_before_compaction() -> (
    None
):
    tool = LLMToolDefinition(
        name="execute",
        description="Execute a geospatial operation.",
        parameters_json_schema={
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    )
    request = LLMRequest(
        model="bounded-model",
        messages=[{"role": "user", "content": "Find the target."}],
        tools=[tool],
        response_json_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
        metadata={
            "context_window_tokens": 2048,
            "maximum_output_tokens": 256,
            "context_profile_source": "provider_metadata",
        },
    )

    usage = compute_context_usage(request, provider="test")

    assert usage.tool_schema_tokens > 0
    assert usage.response_schema_tokens > 0
    assert usage.estimated_input_tokens > usage.current_conversation_tokens
    assert usage.usable_prompt_budget_tokens == 1280
    assert usage.usage_percent is not None

###############################################################################
def test_embedded_response_schema_is_counted_once_as_a_message() -> None:
    messages = [
        {"role": "system", "content": "Extract the requested object."},
        {
            "role": "system",
            "content": '{"type":"object","properties":{"answer":{"type":"string"}}}',
        },
        {"role": "user", "content": "Hello"},
    ]
    request = LLMRequest(
        model="deepseek-v4-flash",
        messages=messages,
        response_json_schema={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
        },
        metadata={RESPONSE_SCHEMA_EMBEDDED_METADATA_KEY: True},
    )

    usage = compute_context_usage(request, provider="opencode-go")

    assert usage.response_schema_tokens == 0
    assert usage.estimated_input_tokens == estimate_message_tokens(messages)

###############################################################################
def test_provider_reported_input_and_output_replace_estimate_without_losing_it() -> (
    None
):
    usage = compute_context_usage(
        _request(
            "hello",
            model="reported-model",
            metadata={
                "context_window_tokens": 4096,
                "maximum_output_tokens": 512,
                "context_profile_source": "provider_metadata",
            },
        ),
        provider="test",
    )

    updated = apply_reported_usage(
        usage,
        {"usage": {"prompt_tokens": 700, "completion_tokens": 42}},
    )

    assert updated.estimated_input_tokens != 700
    assert updated.reported_input_tokens == 700
    assert updated.reported_output_tokens == 42
    assert updated.effective_input_tokens == 700
    assert updated.peak_request_tokens == 700
    assert updated.total_input_tokens == 700
    assert updated.total_output_tokens == 42
    assert updated.usage_source == "provider_reported"
    assert updated.usage_percent == round(700 / 4096 * 100, 1)

###############################################################################
def test_output_only_provider_usage_is_hybrid() -> None:
    usage = compute_context_usage(_request("hello"), provider="test")
    updated = apply_reported_usage(usage, {"eval_count": 19})

    assert updated.reported_input_tokens is None
    assert updated.reported_output_tokens == 19
    assert updated.usage_source == "hybrid"
    assert updated.estimated_input_tokens == updated.effective_input_tokens
    assert updated.total_output_tokens == 19

###############################################################################
def test_nested_provider_usage_is_preserved_from_stream_completion_payload() -> None:
    usage = compute_context_usage(
        _request(
            "hello",
            model="nested-usage-model",
            metadata={
                "context_window_tokens": 4096,
                "maximum_output_tokens": 512,
                "context_profile_source": "provider_metadata",
            },
        ),
        provider="test",
    )

    updated = apply_reported_usage(
        usage,
        {"response": {"usage": {"input_tokens": 700, "output_tokens": 42}}},
    )

    assert updated.reported_input_tokens == 700
    assert updated.reported_output_tokens == 42
    assert updated.usage_source == "provider_reported"
    assert updated.usage_percent == round(700 / 4096 * 100, 1)

###############################################################################
def test_context_usage_percent_uses_model_limit_and_can_show_overage() -> None:
    assert calculate_context_usage_percent(700, 4096) == round(700 / 4096 * 100, 1)
    assert calculate_context_usage_percent(5000, 4096) == round(5000 / 4096 * 100, 1)
    assert calculate_context_usage_percent(700, None) is None

###############################################################################
def test_prepare_request_compacts_explicitly_bounded_history_and_preserves_current_input() -> (
    None
):
    request = LLMRequest(
        model="custom-alias",
        messages=[
            {"role": "system", "content": "system"},
            *[{"role": "user", "content": "x" * 2000} for _ in range(20)],
            {"role": "user", "content": "CURRENT"},
        ],
        metadata={
            "context_window_tokens": 4096,
            "maximum_output_tokens": 512,
            "context_profile_source": "provider_metadata",
        },
    )
    prepared = prepare_request(request, provider="test")

    assert len(prepared.messages) < len(request.messages)
    assert prepared.messages[-1]["content"] == "CURRENT"
    assert any(
        str(item.get("content")).startswith(build_compacted_history_summary(""))
        for item in prepared.messages
    )
    assert prepared.metadata["_context_compaction_applied"] is True

###############################################################################
def test_prepare_request_does_not_invent_limit_for_unknown_model() -> None:
    request = LLMRequest(
        model="unknown-small",
        messages=[
            {"role": "system", "content": "system"},
            *[{"role": "user", "content": "x" * 2000} for _ in range(20)],
            {"role": "user", "content": "CURRENT"},
        ],
    )

    prepared = prepare_request(request, provider="test")

    assert prepared.messages == request.messages

###############################################################################
def test_unknown_model_rejects_oversized_current_request_without_inventing_capacity() -> (
    None
):
    request = _request("x" * 200_000)
    with pytest.raises(LLMContextLimitError):
        prepare_request(request, provider="unknown")
    usage = compute_context_usage(request, provider="unknown")
    assert usage.model_context_limit is None
    assert usage.usage_percent is None

###############################################################################
def test_unknown_model_compacts_history_to_application_input_ceiling() -> None:
    request = LLMRequest(
        model="unknown",
        messages=[
            {"role": "system", "content": "Stable instructions"},
            *[{"role": "user", "content": "old" * 4000} for _ in range(50)],
            {"role": "user", "content": "Show Rome"},
        ],
    )
    prepared = prepare_request(request, provider="unknown")
    assert (
        compute_context_usage(prepared, provider="unknown").estimated_input_tokens
        <= 32_768
    )
    assert prepared.messages[-1]["content"] == "Show Rome"
    assert prepared.metadata["_context_compaction_applied"] is True

###############################################################################
def test_context_limit_failure_preserves_preflight_usage() -> None:
    request = _request(
        "x" * 100_000,
        model="bounded-model",
        metadata={
            "context_window_tokens": 1024,
            "maximum_output_tokens": 256,
            "context_profile_source": "provider_metadata",
        },
    )

    with pytest.raises(LLMContextLimitError) as error:
        prepare_request(request, provider="test")

    assert error.value.context_usage is not None
    assert error.value.context_usage["estimated_input_tokens"] > 0
    assert error.value.context_usage["usable_prompt_budget_tokens"] == 256