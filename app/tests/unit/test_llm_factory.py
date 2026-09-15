from __future__ import annotations

from types import SimpleNamespace

import pytest

from server.services.llm.factory import LLMFactory
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.opencode_provider import OpenCodeProvider
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.transport import LLMTransportPolicy
from server.services.llm.deepseek_provider import DeepSeekProvider

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
