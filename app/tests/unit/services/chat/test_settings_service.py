from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from server.domain.chat import ModelSettingsUpdateRequest
from server.services.chat.settings_service import (
    ChatSettingsService,
    ChatSettingsValidationError,
)


@dataclass
class EncryptedValue:
    value: str
    key_version: str


@dataclass
class FakeSettingsRecord:
    active_provider_mode: str = "cloud"
    chat_model_provider: str = "openai"
    chat_model_name: str = "gpt-4.1-mini"
    parser_model_provider: str = "google"
    parser_model_name: str = "gemini-2.5-flash"
    agent_model_provider: str = "openai"
    agent_model_name: str = "gpt-4.1"
    ollama_url: str = "http://localhost:11434"
    openai_base_url: str | None = "https://openai.example/v1"
    google_base_url: str | None = "https://google.example/v1"


class FakeSettingsRepository:
    def __init__(self, record: FakeSettingsRecord | None = None) -> None:
        self.record = record or FakeSettingsRecord()
        self.last_update: dict[str, Any] | None = None

    def get_or_create(self) -> FakeSettingsRecord:
        return self.record

    def update(self, **kwargs: Any) -> FakeSettingsRecord:
        self.last_update = kwargs
        for key, value in kwargs.items():
            setattr(self.record, key, value)
        return self.record


class FakeCredentialsRepository:
    def __init__(self) -> None:
        self.deactivated: list[tuple[str, str]] = []
        self.upserts: list[tuple[str, str, str, str]] = []

    def list_active(self) -> list[Any]:
        return []

    def deactivate(self, *, provider: str, label: str) -> None:
        self.deactivated.append((provider, label))

    def upsert(
        self,
        *,
        provider: str,
        label: str,
        encrypted_value: str,
        key_version: str,
    ) -> None:
        self.upserts.append((provider, label, encrypted_value, key_version))


class FakeCryptoService:
    def encrypt(self, value: str) -> EncryptedValue:
        return EncryptedValue(value=f"enc:{value}", key_version="v1")

    def decrypt(self, value: str) -> str:
        return value


class FakeModelLibraryService:
    def __init__(self, local_model_ids: set[str] | None = None) -> None:
        self.local_model_ids = local_model_ids or set()

    def list_models(self, *, ollama_url: str) -> dict[str, list[dict[str, object]]]:
        return {
            "cloud": [],
            "local": [
                {
                    "id": model_id,
                    "name": model_id,
                    "description": model_id,
                    "provider": "ollama",
                    "capabilities": [],
                    "metadata": {},
                }
                for model_id in sorted(self.local_model_ids)
            ],
        }


def build_service(
    *,
    settings_repo: FakeSettingsRepository | None = None,
    model_library_service: FakeModelLibraryService | None = None,
    credentials_repo: FakeCredentialsRepository | None = None,
) -> ChatSettingsService:
    return ChatSettingsService(
        settings_repo=settings_repo,  # type: ignore[arg-type]
        credentials_repo=credentials_repo or FakeCredentialsRepository(),  # type: ignore[arg-type]
        crypto_service=FakeCryptoService(),  # type: ignore[arg-type]
        model_library_service=model_library_service or FakeModelLibraryService(),  # type: ignore[arg-type]
    )


def test_partial_update_preserves_existing_settings_when_fields_are_omitted() -> None:
    settings_repo = FakeSettingsRepository()
    service = build_service(settings_repo=settings_repo)

    service.update_settings(ModelSettingsUpdateRequest(chat_model_name="gpt-4.1"))

    assert settings_repo.last_update == {
        "active_provider_mode": "cloud",
        "chat_model_provider": "openai",
        "chat_model_name": "gpt-4.1",
        "parser_model_provider": "google",
        "parser_model_name": "gemini-2.5-flash",
        "agent_model_provider": "openai",
        "agent_model_name": "gpt-4.1",
        "ollama_url": "http://localhost:11434",
        "openai_base_url": "https://openai.example/v1",
        "google_base_url": "https://google.example/v1",
    }


def test_updating_only_credentials_preserves_provider_models_and_base_urls() -> None:
    settings_repo = FakeSettingsRepository()
    credentials_repo = FakeCredentialsRepository()
    service = build_service(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
    )

    service.update_settings(
        ModelSettingsUpdateRequest(credentials={"openai": {"api_key": " secret "}})
    )

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["chat_model_provider"] == "openai"
    assert settings_repo.last_update["chat_model_name"] == "gpt-4.1-mini"
    assert settings_repo.last_update["parser_model_provider"] == "google"
    assert settings_repo.last_update["agent_model_name"] == "gpt-4.1"
    assert settings_repo.last_update["openai_base_url"] == "https://openai.example/v1"
    assert settings_repo.last_update["google_base_url"] == "https://google.example/v1"
    assert credentials_repo.upserts == [("openai", "api_key", "enc:secret", "v1")]


def test_local_chat_model_validation_rejects_unavailable_ollama_model() -> None:
    service = build_service(model_library_service=FakeModelLibraryService({"llama3.2"}))

    with pytest.raises(ChatSettingsValidationError, match="not available from Ollama"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                chat_model_provider="ollama",
                chat_model_name="missing-model",
            )
        )


def test_local_embedding_model_validation_rejects_unavailable_ollama_model() -> None:
    service = build_service(model_library_service=FakeModelLibraryService({"llama3.2"}))

    with pytest.raises(ChatSettingsValidationError, match="not available from Ollama"):
        service.update_settings(
            ModelSettingsUpdateRequest(
                parser_model_provider="ollama",
                parser_model_name="missing-parser",
            )
        )


def test_available_local_models_allow_update() -> None:
    settings_repo = FakeSettingsRepository()
    service = build_service(
        settings_repo=settings_repo,
        model_library_service=FakeModelLibraryService({"llama3.2", "nomic-embed-text"}),
    )

    service.update_settings(
        ModelSettingsUpdateRequest(
            active_provider_mode="local",
            chat_model_provider="ollama",
            chat_model_name="llama3.2",
            parser_model_provider="ollama",
            parser_model_name="llama3.2",
            agent_model_provider="ollama",
            agent_model_name="llama3.2",
        )
    )

    assert settings_repo.last_update is not None
    assert settings_repo.last_update["active_provider_mode"] == "local"
    assert settings_repo.last_update["chat_model_provider"] == "ollama"
    assert settings_repo.last_update["chat_model_name"] == "llama3.2"
