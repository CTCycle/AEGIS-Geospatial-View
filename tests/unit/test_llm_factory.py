from __future__ import annotations

from types import SimpleNamespace

import pytest

from AEGIS.server.services.llm.factory import LLMFactory


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


def test_openai_credential_is_read_from_repository(monkeypatch) -> None:
    monkeypatch.setattr(
        "AEGIS.server.services.llm.factory.OpenAIProvider",
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
        "AEGIS.server.services.llm.factory.GoogleProvider",
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
