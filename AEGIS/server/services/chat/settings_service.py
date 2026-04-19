from __future__ import annotations

from typing import Any

from AEGIS.server.domain.chat import ModelSettingsResponse
from AEGIS.server.repositories.credentials import CredentialRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.cryptography import CredentialEncryptionService


class ChatSettingsService:
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository | None = None,
        credentials_repo: CredentialRepository | None = None,
        crypto_service: CredentialEncryptionService | None = None,
    ) -> None:
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.credentials_repo = credentials_repo or CredentialRepository()
        self.crypto_service = crypto_service or CredentialEncryptionService()

    def get_settings(self) -> ModelSettingsResponse:
        record = self.settings_repo.get_or_create()
        active_credentials = self.credentials_repo.list_active()
        credential_presence: dict[str, dict[str, bool]] = {}
        for item in active_credentials:
            provider_bucket = credential_presence.setdefault(item.provider, {})
            provider_bucket[item.label] = True
        return ModelSettingsResponse(
            active_provider_mode=record.active_provider_mode,  # type: ignore[arg-type]
            chat_model_provider=record.chat_model_provider,
            chat_model_name=record.chat_model_name,
            parser_model_provider=record.parser_model_provider,
            parser_model_name=record.parser_model_name,
            agent_model_provider=record.agent_model_provider,
            agent_model_name=record.agent_model_name,
            ollama_url=record.ollama_url,
            openai_base_url=record.openai_base_url,
            google_base_url=record.google_base_url,
            credentials=credential_presence,
        )

    def get_ollama_url(self) -> str:
        record = self.settings_repo.get_or_create()
        return record.ollama_url

    def update_settings(self, payload: dict[str, Any]) -> ModelSettingsResponse:
        credentials = (
            payload.get("credentials")
            if isinstance(payload.get("credentials"), dict)
            else {}
        )
        for provider, labels in credentials.items():
            if not isinstance(labels, dict):
                continue
            for label, raw_value in labels.items():
                if not isinstance(raw_value, str):
                    continue
                if not raw_value.strip():
                    self.credentials_repo.deactivate(
                        provider=str(provider), label=str(label)
                    )
                    continue
                encrypted = self.crypto_service.encrypt(raw_value.strip())
                self.credentials_repo.upsert(
                    provider=str(provider),
                    label=str(label),
                    encrypted_value=encrypted.value,
                    key_version=encrypted.key_version,
                )
        self.settings_repo.update(
            active_provider_mode=str(payload.get("active_provider_mode") or "local"),
            chat_model_provider=str(payload.get("chat_model_provider") or "ollama"),
            chat_model_name=str(payload.get("chat_model_name") or "llama3.2"),
            parser_model_provider=str(payload.get("parser_model_provider") or "ollama"),
            parser_model_name=str(payload.get("parser_model_name") or "llama3.2"),
            agent_model_provider=str(payload.get("agent_model_provider") or "ollama"),
            agent_model_name=str(payload.get("agent_model_name") or "llama3.2"),
            ollama_url=str(payload.get("ollama_url") or "http://localhost:11434"),
            openai_base_url=(
                str(payload.get("openai_base_url"))
                if payload.get("openai_base_url")
                else None
            ),
            google_base_url=(
                str(payload.get("google_base_url"))
                if payload.get("google_base_url")
                else None
            ),
        )
        return self.get_settings()
