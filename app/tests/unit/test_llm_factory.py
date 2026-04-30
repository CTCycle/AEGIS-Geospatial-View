from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.services.llm.factory import LLMFactory
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest


class _SettingsRepo:
    def get_or_create(self):  # noqa: ANN201
        return SimpleNamespace(
            ollama_url="http://localhost:11434",
            openai_base_url="https://api.openai.test",
            google_base_url="https://generativelanguage.googleapis.test",
        )


class _CredentialsRepo:
    def __init__(self, mapping: dict[tuple[str, str], str]) -> None:
        self.mapping = mapping
        self.mark_used_calls: list[tuple[str, str]] = []

    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        value = self.mapping.get((provider, label))
        if value is None:
            return None
        return SimpleNamespace(encrypted_value=value)

    def mark_used(self, *, provider: str, label: str) -> None:
        self.mark_used_calls.append((provider, label))


class _Crypto:
    def decrypt(self, encrypted_value: str) -> str:
        return f"decrypted:{encrypted_value}"


class _FailingCrypto:
    def decrypt(self, encrypted_value: str) -> str:  # noqa: ARG002
        raise ValueError("bad key")


def test_openai_credential_is_read_from_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.services.llm.factory.OpenAIProvider",
        lambda *, api_key, base_url: (api_key, base_url),
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


def test_google_credential_is_read_from_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "server.services.llm.factory.GoogleProvider",
        lambda *, api_key, base_url: (api_key, base_url),
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


def test_missing_credentials_follow_current_failure_path() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    with pytest.raises(ValueError, match="OpenAI credentials are not configured"):
        factory.get_provider("openai")


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


def test_get_provider_returns_ollama_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("ollama")
    assert isinstance(provider, OllamaProvider)


def test_get_provider_returns_openai_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({("openai", "api_key"): "enc-openai"}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("openai")
    assert isinstance(provider, OpenAIProvider)


def test_get_provider_returns_google_provider_type() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({("google", "api_key"): "enc-google"}),
        crypto_service=_Crypto(),
    )

    provider = factory.get_provider("google")
    assert isinstance(provider, GoogleProvider)


def test_chat_only_provider_blocks_structured_output() -> None:
    factory = LLMFactory(
        settings_repo=_SettingsRepo(),
        credentials_repo=_CredentialsRepo({}),
        crypto_service=_Crypto(),
    )
    provider = factory.get_chat_provider("ollama")
    request = LLMRequest(model="test", messages=[{"role": "user", "content": "x"}])

    with pytest.raises(RuntimeError, match="Structured extraction is forbidden"):
        provider.structured_output(request, schema=dict)
