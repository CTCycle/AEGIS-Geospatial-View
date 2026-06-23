from __future__ import annotations

from dataclasses import dataclass

from server.services.chat import model_library as model_library_module
from server.services.chat.model_library import (
    ChatModelLibraryService,
    ModelLibrarySourceError,
)
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.types import ModelDescriptor


###############################################################################
@dataclass
class _DeepSeekProviderStub:
    models: list[ModelDescriptor]

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return self.models


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
    def __init__(self, *, base_url: str, tool_capability_cache=None) -> None:  # noqa: ANN001
        self.base_url = base_url
        self.tool_capability_cache = tool_capability_cache
        self.last_list_models_error = "Unable to reach Ollama."

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        type(self).calls += 1
        return []


###############################################################################
def test_list_models_reports_ollama_unreachable_without_dropping_cloud_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        model_library_module,
        "OllamaProvider",
        _OllamaProviderUnavailableStub,
    )
    service = ChatModelLibraryService(ollama_unavailable_ttl_s=30.0)

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
    service = ChatModelLibraryService(ollama_unavailable_ttl_s=30.0)

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
        raise AssertionError("Expected ModelLibrarySourceError for unavailable DeepSeek catalog.")


###############################################################################
def test_normalize_ollama_url_rewrites_localhost() -> None:
    assert (
        ChatModelLibraryService.normalize_ollama_url("http://localhost:11434")
        == "http://127.0.0.1:11434"
    )
