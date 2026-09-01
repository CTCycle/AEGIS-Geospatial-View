from __future__ import annotations

from types import SimpleNamespace

from server.services.llm.context_profile_resolver import ModelContextProfileResolver


###############################################################################
class _SettingsRepository:
    # -------------------------------------------------------------------------
    def get_required(self):  # noqa: ANN201
        return SimpleNamespace(ollama_url="http://ollama.test")


###############################################################################
class _ModelLibrary:
    # -------------------------------------------------------------------------
    def __init__(self, descriptor: dict[str, object] | None) -> None:
        self.descriptor = descriptor
        self.find_calls = 0

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_ollama_url(value: str) -> str:
        return value

    # -------------------------------------------------------------------------
    def find_model(self, **kwargs):  # noqa: ANN003, ANN201
        self.find_calls += 1
        assert kwargs["ollama_url"] == "http://ollama.test"
        return self.descriptor


###############################################################################
def test_resolver_prefers_exact_static_catalog_without_dynamic_lookup() -> None:
    library = _ModelLibrary(None)
    resolver = ModelContextProfileResolver(
        model_library_service=library,
        settings_repo=_SettingsRepository(),
    )

    profile = resolver.resolve("openai", "gpt-4.1")

    assert profile is not None
    assert profile.context_window_tokens == 1_047_576
    assert profile.metadata_source == "openai_model_catalog"
    assert library.find_calls == 0


###############################################################################
def test_resolver_caches_exact_dynamic_provider_metadata() -> None:
    library = _ModelLibrary(
        {
            "provider": "opencode-go",
            "name": "runtime-model",
            "metadata": {
                "context_window_tokens": 8192,
                "max_output_tokens": 512,
                "context_profile_source": "provider_models_api",
            },
        }
    )
    resolver = ModelContextProfileResolver(
        model_library_service=library,
        settings_repo=_SettingsRepository(),
    )

    first = resolver.resolve("opencode-go", "runtime-model")
    second = resolver.resolve("opencode-go", "runtime-model")

    assert first == second
    assert first is not None
    assert first.context_window_tokens == 8192
    assert first.maximum_output_tokens == 512
    assert first.metadata_source == "provider_models_api"
    assert library.find_calls == 1


###############################################################################
def test_resolver_keeps_missing_dynamic_context_unknown() -> None:
    library = _ModelLibrary({"provider": "opencode-go", "name": "custom-4k"})
    resolver = ModelContextProfileResolver(
        model_library_service=library,
        settings_repo=_SettingsRepository(),
    )

    profile = resolver.resolve("opencode-go", "custom-4k")

    assert profile is None
    assert library.find_calls == 1
