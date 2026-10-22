from __future__ import annotations
from dataclasses import dataclass
from server.services.chat import model_library as model_library_module
from server.services.chat.model_library import ChatModelLibraryService, ModelLibrarySourceError
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.types import ModelDescriptor
from typing import Any
import pytest
from server.contracts.chat import ModelSettingsUpdateRequest
from server.services.chat.settings_service import ChatSettingsService, ChatSettingsValidationError

# --- test_model_library_service.py ---



###############################################################################
@dataclass
class _DeepSeekProviderStub:
    models: list[ModelDescriptor]

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return self.models

###############################################################################
@dataclass
class _FlakyDynamicProvider:
    responses: list[list[ModelDescriptor] | Exception]
    calls: int = 0

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response

###############################################################################
class _ProviderFactoryStub:

    # -------------------------------------------------------------------------
    def __init__(self, provider: _DeepSeekProviderStub | Exception) -> None:
        self.provider = provider

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str):  # noqa: ANN001
        assert provider == "deepseek"
        if isinstance(self.provider, Exception):
            raise self.provider
        return self.provider

###############################################################################
class _OllamaProviderUnavailableStub:
    calls = 0

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        base_url: str,
        tool_capability_cache=None,  # noqa: ANN001
        transport_policy=None,  # noqa: ANN001
    ) -> None:
        self.base_url = base_url
        self.tool_capability_cache = tool_capability_cache
        self.transport_policy = transport_policy
        self.last_list_models_error = "Unable to reach Ollama."

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        type(self).calls += 1
        return []

###############################################################################
def _build_service() -> ChatModelLibraryService:
    return ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(_DeepSeekProviderStub([])),
        ollama_unavailable_ttl_s=30.0,
    )

###############################################################################
def test_list_models_reports_ollama_unreachable_without_dropping_cloud_catalog(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = _build_service()

    response = service.list_models(ollama_url="http://localhost:11434")

    assert response["cloud"]
    assert response["local"] == []
    assert response["sources"]["ollama"]["reachable"] is False
    assert response["sources"]["ollama"]["ok"] is False

###############################################################################
def test_list_models_caches_ollama_unavailable_result(monkeypatch) -> None:
    _OllamaProviderUnavailableStub.calls = 0
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = _build_service()

    first = service.list_models(ollama_url="http://localhost:11434")
    second = service.list_models(ollama_url="http://localhost:11434")

    assert first["sources"]["ollama"]["reachable"] is False
    assert second["sources"]["ollama"]["reachable"] is False
    assert _OllamaProviderUnavailableStub.calls == 1

###############################################################################
def test_list_models_reports_deepseek_failure_in_sources(monkeypatch) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(
            LLMConfigurationError("DeepSeek credentials are not configured.")
        )
    )

    response = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )

    assert response["cloud"]
    assert response["sources"]["deepseek"]["ok"] is False
    assert "DeepSeek credentials" in str(response["sources"]["deepseek"]["message"])

###############################################################################
def test_dynamic_catalog_failure_can_recover_and_success_remains_cached(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    dynamic_provider = _FlakyDynamicProvider(
        responses=[
            LLMConfigurationError("Transient catalog failure."),
            [
                ModelDescriptor(
                    name="recovered-model",
                    description="Recovered model",
                    provider="deepseek",
                )
            ],
        ]
    )
    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(dynamic_provider),
    )

    first = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )
    second = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )
    third = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )

    assert first["sources"]["deepseek"]["ok"] is False
    assert second["sources"]["deepseek"]["ok"] is True
    assert any(item["id"] == "recovered-model" for item in second["cloud"])
    assert third["sources"]["deepseek"]["ok"] is True
    assert dynamic_provider.calls == 2

    service.invalidate_dynamic_catalogs()
    fourth = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )

    assert fourth["sources"]["deepseek"]["ok"] is True
    assert dynamic_provider.calls == 3

###############################################################################
def test_find_model_raises_when_deepseek_catalog_cannot_be_loaded(monkeypatch) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(
            LLMConfigurationError("DeepSeek credentials are not configured.")
        )
    )

    try:
        service.find_model(
            provider="deepseek",
            model_name="deepseek-chat",
            ollama_url="http://127.0.0.1:11434",
            require_provider_availability=True,
        )
    except ModelLibrarySourceError as exc:
        assert "DeepSeek credentials" in str(exc)
    else:
        raise AssertionError(
            "Expected ModelLibrarySourceError for unavailable DeepSeek catalog."
        )

###############################################################################
def test_find_model_loads_dynamic_metadata_for_context_profile_lookup(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(
            _DeepSeekProviderStub(
                [
                    ModelDescriptor(
                        name="runtime-model",
                        description="Runtime model",
                        provider="deepseek",
                    )
                ]
            )
        )
    )
    result = service.find_model(
        provider="deepseek",
        model_name="runtime-model",
        ollama_url="http://127.0.0.1:11434",
    )

    assert result is not None
    assert result["name"] == "runtime-model"

###############################################################################
def test_find_cached_model_never_refreshes_dynamic_provider(monkeypatch) -> None:

    ###############################################################################
    class _ProviderThatMustNotBeCalled:

        # -------------------------------------------------------------------------
        def list_models(self):  # noqa: ANN201
            raise AssertionError("context lookup must not refresh a provider catalog")

    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(_ProviderThatMustNotBeCalled()),
    )
    service._dynamic_catalog_cache["deepseek"] = (
        model_library_module._CachedModelDescriptors(  # pyright: ignore[reportPrivateUsage]
            expires_at=10**12,
            models=[
                ModelDescriptor(
                    name="cached-model",
                    description="Cached model",
                    provider="deepseek",
                    metadata={"context_window_tokens": 8192},
                )
            ],
            source={"ok": True},
        )
    )

    result = service.find_cached_model(
        provider="deepseek",
        model_name="cached-model",
        ollama_url="http://127.0.0.1:11434",
    )

    assert result is not None
    assert result["name"] == "cached-model"

###############################################################################
def test_find_cached_model_returns_none_without_catalog_refresh() -> None:
    service = _build_service()

    assert (
        service.find_cached_model(
            provider="opencode-go",
            model_name="uncached-model",
            ollama_url="http://127.0.0.1:11434",
        )
        is None
    )

###############################################################################
def test_expired_dynamic_catalog_failure_does_not_reuse_stale_model() -> None:
    service = ChatModelLibraryService(
        provider_factory=_ProviderFactoryStub(
            LLMConfigurationError("DeepSeek credentials are not configured.")
        )
    )
    service._dynamic_catalog_cache["deepseek"] = (
        model_library_module._CachedModelDescriptors(  # pyright: ignore[reportPrivateUsage]
            expires_at=0,
            models=[
                ModelDescriptor(
                    name="stale-model",
                    description="Stale model",
                    provider="deepseek",
                )
            ],
            source={"ok": True, "stale": False},
        )
    )

    response = service.list_models(
        ollama_url="http://127.0.0.1:11434",
        cloud_provider="deepseek",
    )

    assert all(item["id"] != "stale-model" for item in response["cloud"])
    assert response["sources"]["deepseek"]["ok"] is False

###############################################################################
def test_normalize_ollama_url_rewrites_localhost() -> None:
    assert (
        ChatModelLibraryService.normalize_ollama_url("http://localhost:11434")
        == "http://127.0.0.1:11434"
    )

###############################################################################
def test_ollama_selected_context_enrichment_updates_the_shared_model_cache(
    monkeypatch,
) -> None:

    ###############################################################################
    class _OllamaProviderWithContext:

        # -------------------------------------------------------------------------
        def __init__(self, **_kwargs) -> None:  # noqa: ANN003
            self.last_list_models_error = None

        # -------------------------------------------------------------------------
        def list_models(self) -> list[ModelDescriptor]:
            return [
                ModelDescriptor(
                    name="local-alias",
                    description="Local model",
                    provider="ollama",
                )
            ]

        # -------------------------------------------------------------------------
        def get_model_context_metadata(self, model: str) -> dict[str, object]:
            assert model == "local-alias"
            return {
                "context_window_tokens": 40_960,
                "context_profile_source": "ollama_show_model_info",
                "context_metadata_authority": "provider",
            }

    monkeypatch.setattr(
        model_library_module, "OllamaProvider", _OllamaProviderWithContext
    )
    service = _build_service()
    ollama_url = "http://127.0.0.1:11434"

    service.list_models(ollama_url=ollama_url)
    selected = service.find_model(
        provider="ollama",
        model_name="local-alias",
        ollama_url=ollama_url,
    )
    cached = service.find_cached_model(
        provider="ollama",
        model_name="local-alias",
        ollama_url=ollama_url,
    )

    assert selected is not None
    assert selected["context_window_tokens"] == 40_960
    assert selected["context_metadata_authority"] == "provider"
    assert cached is not None
    assert cached["context_window_tokens"] == 40_960

# --- test_settings_service.py ---




###############################################################################
@dataclass
class EncryptedValue:
    value: str
    key_version: str

###############################################################################
@dataclass
class FakeCredentialRecord:
    provider: str
    label: str
    encrypted_value: str

###############################################################################
@dataclass
class FakeSettingsRecord:
    active_provider_mode: str = "cloud"
    agent_model_provider: str = "openai"
    agent_model_name: str = "gpt-4.1"
    ollama_url: str = "http://127.0.0.1:11434"
    openai_base_url: str | None = "https://openai.example/v1"
    google_base_url: str | None = "https://google.example/v1"
    deepseek_base_url: str | None = "https://deepseek.example/v1"

###############################################################################
class FakeSettingsRepository:

    # -------------------------------------------------------------------------
    def __init__(self, record: FakeSettingsRecord | None = None) -> None:
        self.record = record or FakeSettingsRecord()
        self.last_update: dict[str, Any] | None = None

    # -------------------------------------------------------------------------
    def get_required(self) -> FakeSettingsRecord:
        return self.record

    # -------------------------------------------------------------------------
    def update(self, **kwargs: Any) -> FakeSettingsRecord:
        self.last_update = dict(kwargs)
        for key, value in kwargs.items():
            setattr(self.record, key, value)
        return self.record

###############################################################################
class FakeCredentialsRepository:

    # -------------------------------------------------------------------------
    def __init__(self, active_items: list[FakeCredentialRecord] | None = None) -> None:
        self.active_items = active_items or []
        self.deactivated: list[tuple[str, str]] = []
        self.upserts: list[tuple[str, str, str, str]] = []

    # -------------------------------------------------------------------------
    def list_active(self) -> list[Any]:
        return list(self.active_items)

    # -------------------------------------------------------------------------
    def deactivate(self, *, provider: str, label: str) -> None:
        self.deactivated.append((provider, label))

    # -------------------------------------------------------------------------
    def upsert(
        self, *, provider: str, label: str, encrypted_value: str, key_version: str
    ) -> None:
        self.upserts.append((provider, label, encrypted_value, key_version))

###############################################################################
class FakeCryptoService:

    # -------------------------------------------------------------------------
    def encrypt(self, value: str) -> EncryptedValue:
        return EncryptedValue(value=f"enc:{value}", key_version="v1")

    # -------------------------------------------------------------------------
    def decrypt(self, value: str) -> str:
        return value

###############################################################################
class FakeModelLibraryService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        local_model_ids: set[str] | None = None,
        model_overrides: dict[tuple[str, str], dict[str, object]] | None = None,
    ) -> None:
        self.local_model_ids = local_model_ids or set()
        self.model_overrides = model_overrides or {}

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_ollama_url(ollama_url: str) -> str:
        return ollama_url.replace("http://localhost", "http://127.0.0.1")

    # -------------------------------------------------------------------------
    def list_models(
        self, *, ollama_url: str, cloud_provider: str | None = None
    ) -> dict[str, object]:
        _ = cloud_provider
        local = [
            {
                "id": model_id,
                "name": model_id,
                "description": model_id,
                "provider": "ollama",
                "capabilities": ["chat", "structured_output", "tools"],
                "supports_tools": True,
                "supports_structured_output": True,
                "metadata": {},
            }
            | self.model_overrides.get(("ollama", model_id), {})
            for model_id in sorted(self.local_model_ids)
        ]
        cloud = [
            {
                "id": name,
                "name": name,
                "description": name,
                "provider": provider,
                "capabilities": ["chat", "structured_output", "tools"],
                "supports_tools": True,
                "supports_structured_output": True,
                "metadata": {},
            }
            | override
            for (provider, name), override in self.model_overrides.items()
            if provider != "ollama"
        ]
        return {"cloud": cloud, "local": local, "sources": {"ollama": {"ok": True}}}

    # -------------------------------------------------------------------------
    def find_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
        require_provider_availability: bool = False,
    ) -> dict[str, object] | None:
        _ = (ollama_url, require_provider_availability)
        for bucket in self.list_models(ollama_url=ollama_url).values():
            if not isinstance(bucket, list):
                continue
            for item in bucket:
                if item.get("provider") == provider and item.get("name") == model_name:
                    return item
        return None

###############################################################################
class NoLiveCatalogModelLibraryService(FakeModelLibraryService):

    # -------------------------------------------------------------------------
    def find_model(self, **kwargs: Any) -> dict[str, object] | None:
        _ = kwargs
        raise AssertionError("reading settings must not query a live model catalog")

###############################################################################
class NoSelectedModelResolution:

    # -------------------------------------------------------------------------
    def resolve_selected(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("startup validation must not resolve model metadata")

###############################################################################
class UnreadableCredentialCrypto:

    # -------------------------------------------------------------------------
    @staticmethod
    def decrypt(_value: str) -> str:
        raise ValueError("Credential cannot be decrypted with current key.")

###############################################################################
def build_service(
    *,
    settings_repo: FakeSettingsRepository | None = None,
    model_library_service: FakeModelLibraryService | None = None,
    credentials_repo: FakeCredentialsRepository | None = None,
) -> ChatSettingsService:
    return ChatSettingsService(
        settings_repo=settings_repo or FakeSettingsRepository(),  # type: ignore[arg-type]
        credentials_repo=credentials_repo or FakeCredentialsRepository(),  # type: ignore[arg-type]
        crypto_service=FakeCryptoService(),  # type: ignore[arg-type]
        model_library_service=model_library_service or FakeModelLibraryService(),  # type: ignore[arg-type]
    )

###############################################################################
def test_partial_agent_update_preserves_urls_and_credentials_shape() -> None:
    settings_repo = FakeSettingsRepository()
    service = build_service(settings_repo=settings_repo)

    service.update_settings(ModelSettingsUpdateRequest(agent_model_name="gpt-4.1-mini"))

    assert settings_repo.last_update == {
        "active_provider_mode": "cloud",
        "agent_model_provider": "openai",
        "agent_model_name": "gpt-4.1-mini",
        "ollama_url": "http://127.0.0.1:11434",
        "openai_base_url": "https://openai.example/v1",
        "google_base_url": "https://google.example/v1",
        "deepseek_base_url": "https://deepseek.example/v1",
    }

###############################################################################
def test_update_settings_rejects_blank_agent_selection() -> None:
    service = build_service()

    with pytest.raises(ChatSettingsValidationError, match="Agent model provider"):
        service.update_settings(
            ModelSettingsUpdateRequest(agent_model_provider="", agent_model_name="")
        )

###############################################################################
@pytest.mark.parametrize(
    "provider",
    ["OpenAI", " openai", "openai ", "openai-compatible", "opencode_go"],
)
def test_update_settings_rejects_noncanonical_provider_ids(provider: str) -> None:
    service = build_service()

    with pytest.raises(ChatSettingsValidationError, match="Unsupported model provider"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                agent_model_provider=provider,
                agent_model_name="gpt-4.1",
            )
        )

###############################################################################
@pytest.mark.parametrize(
    "provider",
    ["OpenAI", "openai-compatible", "opencode_go", "not-registered"],
)
def test_update_settings_rejects_noncanonical_credential_provider_ids(provider: str) -> None:
    service = build_service()

    with pytest.raises(ChatSettingsValidationError, match="Unsupported credential provider"):
        service.update_settings(
            ModelSettingsUpdateRequest(credentials={provider: {"api_key": "secret"}})
        )

###############################################################################
def test_update_settings_rejects_noncanonical_credential_labels() -> None:
    service = build_service()

    with pytest.raises(ChatSettingsValidationError, match="Unsupported credential label"):
        service.update_settings(
            ModelSettingsUpdateRequest(credentials={"openai": {"token": "secret"}})
        )

###############################################################################
def test_get_settings_preserves_blank_agent_when_no_models_are_available() -> None:
    settings_repo = FakeSettingsRepository(
        FakeSettingsRecord(agent_model_provider="", agent_model_name="")
    )
    service = build_service(settings_repo=settings_repo)

    response = service.get_settings()

    assert response.agent_model_provider == ""
    assert response.agent_model_name == ""
    assert settings_repo.last_update is None

###############################################################################
def test_get_settings_uses_canonical_static_context_without_live_catalog() -> None:
    service = build_service(model_library_service=NoLiveCatalogModelLibraryService())

    response = service.get_settings()

    assert response.selected_model_context.model_dump(mode="json") == {
        "provider": "openai",
        "model": "gpt-4.1",
        "context_window_tokens": 1_047_576,
        "maximum_output_tokens": 32_768,
        "context_profile_source": "openai_model_catalog",
        "context_metadata_authority": "configured",
    }

###############################################################################
def test_validate_persisted_settings_avoids_provider_and_model_lookups() -> None:
    service = build_service(
        settings_repo=FakeSettingsRepository(
            FakeSettingsRecord(
                agent_model_provider="deepseek",
                agent_model_name="deepseek-chat",
            )
        ),
        credentials_repo=FakeCredentialsRepository(
            [FakeCredentialRecord("openai", "api_key", "encrypted")]
        ),
        model_library_service=NoLiveCatalogModelLibraryService(),
    )
    service.context_profile_resolver = NoSelectedModelResolution()  # type: ignore[assignment]

    service.validate_persisted_settings()

###############################################################################
def test_validate_persisted_settings_rejects_unreadable_credentials() -> None:
    service = build_service(
        credentials_repo=FakeCredentialsRepository(
            [FakeCredentialRecord("openai", "api_key", "unreadable")]
        )
    )

    service.crypto_service = UnreadableCredentialCrypto()  # type: ignore[assignment]
    with pytest.raises(ChatSettingsValidationError, match="cannot be decrypted"):
        service.validate_persisted_settings()

###############################################################################
def test_updating_only_credentials_is_allowed_before_first_agent_selection() -> None:
    settings_repo = FakeSettingsRepository(
        FakeSettingsRecord(agent_model_provider="", agent_model_name="")
    )
    credentials_repo = FakeCredentialsRepository()
    service = build_service(
        settings_repo=settings_repo, credentials_repo=credentials_repo
    )

    service.update_settings(
        ModelSettingsUpdateRequest(credentials={"opencode-go": {"api_key": " secret "}})
    )

    assert credentials_repo.upserts == [("opencode-go", "api_key", "enc:secret", "v1")]
    assert settings_repo.last_update is not None
    assert settings_repo.last_update["agent_model_provider"] == ""
    assert settings_repo.last_update["agent_model_name"] == ""

###############################################################################
def test_updating_only_ollama_url_is_allowed_before_first_agent_selection() -> None:
    settings_repo = FakeSettingsRepository(
        FakeSettingsRecord(agent_model_provider="", agent_model_name="")
    )
    service = build_service(settings_repo=settings_repo)

    service.update_settings(
        ModelSettingsUpdateRequest(ollama_url="http://127.0.0.1:11500")
    )

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["ollama_url"] == "http://127.0.0.1:11500"
    assert settings_repo.last_update["agent_model_provider"] == ""

###############################################################################
def test_updating_only_credentials_preserves_selected_agent_and_base_urls() -> None:
    settings_repo = FakeSettingsRepository()
    credentials_repo = FakeCredentialsRepository()
    service = build_service(
        settings_repo=settings_repo, credentials_repo=credentials_repo
    )

    service.update_settings(
        ModelSettingsUpdateRequest(credentials={"openai": {"api_key": " secret "}})
    )

    assert credentials_repo.upserts == [("openai", "api_key", "enc:secret", "v1")]
    assert settings_repo.last_update is not None
    assert settings_repo.last_update["agent_model_provider"] == "openai"
    assert settings_repo.last_update["agent_model_name"] == "gpt-4.1"
    assert settings_repo.last_update["openai_base_url"] == "https://openai.example/v1"

###############################################################################
def test_updating_only_credentials_skips_unrelated_local_model_validation() -> None:
    settings_repo = FakeSettingsRepository(
        FakeSettingsRecord(
            active_provider_mode="local",
            agent_model_provider="ollama",
            agent_model_name="missing-agent",
        )
    )
    credentials_repo = FakeCredentialsRepository()
    service = build_service(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        model_library_service=FakeModelLibraryService({"different-installed-model"}),
    )

    service.update_settings(
        ModelSettingsUpdateRequest(credentials={"tomtom": {"api_key": " key "}})
    )

    assert credentials_repo.upserts == [("tomtom", "api_key", "enc:key", "v1")]
    assert settings_repo.last_update is not None
    assert settings_repo.last_update["agent_model_name"] == "missing-agent"

###############################################################################
def test_local_model_validation_rejects_unavailable_agent_model() -> None:
    service = build_service(model_library_service=FakeModelLibraryService({"llama3.2"}))

    with pytest.raises(ChatSettingsValidationError, match="Selected agent model"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                agent_model_provider="ollama", agent_model_name="missing-agent"
            )
        )

###############################################################################
def test_available_local_model_allows_update() -> None:
    settings_repo = FakeSettingsRepository()
    service = build_service(
        settings_repo=settings_repo,
        model_library_service=FakeModelLibraryService({"llama3.2", "nomic-embed-text"}),
    )

    service.update_settings(
        ModelSettingsUpdateRequest(
            active_provider_mode="local",
            agent_model_provider="ollama",
            agent_model_name="llama3.2",
        )
    )

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["agent_model_provider"] == "ollama"
    assert settings_repo.last_update["agent_model_name"] == "llama3.2"

###############################################################################
def test_agent_model_without_tools_is_rejected() -> None:
    service = build_service(
        model_library_service=FakeModelLibraryService(
            model_overrides={
                ("openai", "no-tools"): {
                    "supports_tools": False,
                    "supports_structured_output": True,
                }
            }
        )
    )

    with pytest.raises(ChatSettingsValidationError, match="native tool calling"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                agent_model_provider="openai", agent_model_name="no-tools"
            )
        )

###############################################################################
def test_agent_model_without_structured_output_is_rejected() -> None:
    service = build_service(
        model_library_service=FakeModelLibraryService(
            model_overrides={
                ("google", "no-structured"): {
                    "supports_tools": True,
                    "supports_structured_output": False,
                }
            }
        )
    )

    with pytest.raises(ChatSettingsValidationError, match="structured output"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                agent_model_provider="google", agent_model_name="no-structured"
            )
        )

###############################################################################
def test_agent_model_with_tools_and_structured_output_is_accepted() -> None:
    settings_repo = FakeSettingsRepository()
    service = build_service(
        settings_repo=settings_repo,
        model_library_service=FakeModelLibraryService(
            model_overrides={
                ("google", "gemini-2.5-pro"): {
                    "supports_tools": True,
                    "supports_structured_output": True,
                }
            }
        ),
    )

    service.update_settings(
        ModelSettingsUpdateRequest(
            agent_model_provider="google", agent_model_name="gemini-2.5-pro"
        )
    )

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["agent_model_name"] == "gemini-2.5-pro"