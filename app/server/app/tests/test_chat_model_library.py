from __future__ import annotations

from dataclasses import dataclass

from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.types import ModelDescriptor


###############################################################################
@dataclass
class _StubProvider:
    models: list[ModelDescriptor]

    # -------------------------------------------------------------------------
    def list_models(self) -> list[ModelDescriptor]:
        return self.models


###############################################################################
class _StubProviderFactory:

    # -------------------------------------------------------------------------
    def __init__(self, models: list[ModelDescriptor]) -> None:
        self.models = models
        self.providers_requested: list[str] = []

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> _StubProvider:
        self.providers_requested.append(provider)
        return _StubProvider(self.models)


###############################################################################
class _StubOllamaCache:
    pass


###############################################################################
def test_list_models_includes_deepseek_models_only_when_requested(monkeypatch) -> None:
    class _StubOllamaProvider:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)

        def list_library_models(self) -> list[ModelDescriptor]:
            return []

        def list_models(self) -> list[ModelDescriptor]:
            return []

    monkeypatch.setattr(
        "server.services.chat.model_library.OllamaProvider",
        _StubOllamaProvider,
    )
    factory = _StubProviderFactory(
        [
            ModelDescriptor(
                name="deepseek-v4-flash",
                description="DeepSeek Flash",
                provider="deepseek",
                capabilities=["chat", "tools", "structured_output"],
                metadata={"tool_support_source": "provider"},
            )
        ]
    )
    service = ChatModelLibraryService(
        ollama_tool_capability_cache=_StubOllamaCache(),  # type: ignore[arg-type]
        provider_factory=factory,  # type: ignore[arg-type]
    )

    default_library = service.list_models(ollama_url="http://localhost:11434")
    requested_library = service.list_models(
        ollama_url="http://localhost:11434",
        cloud_provider="deepseek",
    )

    assert not any(model["provider"] == "deepseek" for model in default_library["cloud"])
    assert any(model["provider"] == "deepseek" for model in requested_library["cloud"])
    assert factory.providers_requested == ["deepseek"]


###############################################################################
def test_find_model_loads_dynamic_deepseek_catalog(monkeypatch) -> None:
    class _StubOllamaProvider:
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            _ = (args, kwargs)

        def list_library_models(self) -> list[ModelDescriptor]:
            return []

        def list_models(self) -> list[ModelDescriptor]:
            return []

    monkeypatch.setattr(
        "server.services.chat.model_library.OllamaProvider",
        _StubOllamaProvider,
    )
    service = ChatModelLibraryService(
        provider_factory=_StubProviderFactory(
            [
                ModelDescriptor(
                    name="deepseek-v4-pro",
                    description="DeepSeek Pro",
                    provider="deepseek",
                    capabilities=["chat", "tools", "structured_output"],
                    metadata={"tool_support_source": "provider"},
                )
            ]
        )  # type: ignore[arg-type]
    )

    model = service.find_model(
        provider="deepseek",
        model_name="deepseek-v4-pro",
        ollama_url="http://localhost:11434",
    )

    assert model is not None
    assert model["provider"] == "deepseek"
    assert model["supports_tools"] is True
