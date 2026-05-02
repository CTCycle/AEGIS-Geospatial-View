from __future__ import annotations

from dataclasses import dataclass

from server.common.constants import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    DEFAULT_MODEL_PROVIDER_MODE,
    OLLAMA_DEFAULT_HOST,
)
from server.domain.chat import ModelSettingsUpdateRequest
from server.services.chat.settings_service import ChatSettingsService


@dataclass
class _EncryptedValue:
    value: str
    key_version: str


class _FakeSettingsRecord:
    active_provider_mode = DEFAULT_MODEL_PROVIDER_MODE
    chat_model_provider = DEFAULT_MODEL_PROVIDER
    chat_model_name = DEFAULT_MODEL_NAME
    parser_model_provider = DEFAULT_MODEL_PROVIDER
    parser_model_name = DEFAULT_MODEL_NAME
    agent_model_provider = DEFAULT_MODEL_PROVIDER
    agent_model_name = DEFAULT_MODEL_NAME
    ollama_url = OLLAMA_DEFAULT_HOST
    openai_base_url = None
    google_base_url = None


class _FakeSettingsRepository:
    def __init__(self) -> None:
        self.last_update: dict[str, object] | None = None

    def get_or_create(self):
        return _FakeSettingsRecord()

    def update(self, **kwargs):
        self.last_update = kwargs
        return _FakeSettingsRecord()


class _FakeCredentialsRepository:
    def __init__(self) -> None:
        self.deactivated: list[tuple[str, str]] = []
        self.upserts: list[tuple[str, str, str, str]] = []

    def list_active(self):
        return []

    def deactivate(self, *, provider: str, label: str) -> None:
        self.deactivated.append((provider, label))

    def upsert(self, *, provider: str, label: str, encrypted_value: str, key_version: str) -> None:
        self.upserts.append((provider, label, encrypted_value, key_version))


class _FakeCryptoService:
    def encrypt(self, value: str) -> _EncryptedValue:
        return _EncryptedValue(value=f"enc:{value}", key_version="v1")

    def decrypt(self, value: str) -> str:
        return value


def test_update_settings_uses_typed_request_and_defaults() -> None:
    settings_repo = _FakeSettingsRepository()
    service = ChatSettingsService(
        settings_repo=settings_repo,  # type: ignore[arg-type]
        credentials_repo=_FakeCredentialsRepository(),  # type: ignore[arg-type]
        crypto_service=_FakeCryptoService(),  # type: ignore[arg-type]
    )

    payload = ModelSettingsUpdateRequest()
    service.update_settings(payload)

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["active_provider_mode"] == DEFAULT_MODEL_PROVIDER_MODE
    assert settings_repo.last_update["chat_model_provider"] == DEFAULT_MODEL_PROVIDER
    assert settings_repo.last_update["chat_model_name"] == DEFAULT_MODEL_NAME
    assert settings_repo.last_update["ollama_url"] == OLLAMA_DEFAULT_HOST


def test_update_settings_deactivates_blank_credentials_and_upserts_non_blank() -> None:
    credentials_repo = _FakeCredentialsRepository()
    service = ChatSettingsService(
        settings_repo=_FakeSettingsRepository(),  # type: ignore[arg-type]
        credentials_repo=credentials_repo,  # type: ignore[arg-type]
        crypto_service=_FakeCryptoService(),  # type: ignore[arg-type]
    )

    payload = ModelSettingsUpdateRequest(
        credentials={
            "openai": {"api_key": "  "},
            "google": {"api_key": "  secret-token  "},
        }
    )

    service.update_settings(payload)

    assert credentials_repo.deactivated == [("openai", "api_key")]
    assert credentials_repo.upserts == [
        ("google", "api_key", "enc:secret-token", "v1"),
    ]