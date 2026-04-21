from __future__ import annotations

from types import SimpleNamespace

import pytest

from AEGIS.server.services.vector.embedding_factory import EmbeddingFactory


class _Provider:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def embeddings(self, *, model: str, input_text: str) -> list[float]:
        self.calls.append((model, input_text))
        return [1.0, 2.0]


class _LLMFactoryStub:
    def __init__(self) -> None:
        self.provider = _Provider()
        self.last_provider_name: str | None = None

    def get_provider(self, provider: str) -> _Provider:
        self.last_provider_name = provider
        return self.provider


class _SettingsRepoStub:
    def get_or_create(self):  # noqa: ANN201
        return SimpleNamespace(ollama_url="http://localhost:11434")


def test_provider_normalization_and_default_model_selection(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.vector.embedding_factory.get_server_settings",
        lambda: SimpleNamespace(
            vectors=SimpleNamespace(
                default_openai_embedding_model="openai-default",
                default_google_embedding_model="google-default",
                default_ollama_embedding_model="ollama-default",
            )
        ),
    )
    factory = EmbeddingFactory(
        llm_factory=_LLMFactoryStub(),
        settings_repo=_SettingsRepoStub(),
    )

    assert factory.normalize_provider("OpenAI") == "openai"
    assert factory.normalize_provider(" GOOGLE ") == "google"
    assert factory.normalize_provider(None) == "ollama"
    assert factory.resolve_default_model("openai") == "openai-default"
    assert factory.resolve_default_model("google") == "google-default"
    assert factory.resolve_default_model("ollama") == "ollama-default"


def test_ollama_unreachable_guard_blocks_generation(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.vector.embedding_factory.get_server_settings",
        lambda: SimpleNamespace(
            vectors=SimpleNamespace(
                default_openai_embedding_model="openai-default",
                default_google_embedding_model="google-default",
                default_ollama_embedding_model="ollama-default",
            )
        ),
    )
    llm_factory = _LLMFactoryStub()
    factory = EmbeddingFactory(llm_factory=llm_factory, settings_repo=_SettingsRepoStub())
    monkeypatch.setattr(factory, "_is_ollama_reachable", lambda: False)

    with pytest.raises(RuntimeError, match="Ollama is not reachable"):
        factory.get_embedding(provider="ollama", input_text="x", model=None)


def test_get_embedding_returns_tuple_with_selected_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.vector.embedding_factory.get_server_settings",
        lambda: SimpleNamespace(
            vectors=SimpleNamespace(
                default_openai_embedding_model="openai-default",
                default_google_embedding_model="google-default",
                default_ollama_embedding_model="ollama-default",
            )
        ),
    )
    llm_factory = _LLMFactoryStub()
    factory = EmbeddingFactory(llm_factory=llm_factory, settings_repo=_SettingsRepoStub())

    vector, selected_model = factory.get_embedding(
        provider="openai",
        input_text="hello",
        model=None,
    )
    assert vector == [1.0, 2.0]
    assert selected_model == "openai-default"
    assert llm_factory.last_provider_name == "openai"
