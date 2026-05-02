from __future__ import annotations

from server.common.constants import (
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_PROVIDER,
    DEFAULT_MODEL_PROVIDER_MODE,
    OLLAMA_DEFAULT_HOST,
)
from server.domain.chat import ModelSettingsResponse, ModelSettingsUpdateRequest
from server.repositories.credentials import CredentialRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.cryptography import CredentialEncryptionService


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
        credential_health: dict[str, dict[str, str]] = {}
        for item in active_credentials:
            provider_bucket = credential_presence.setdefault(item.provider, {})
            provider_bucket[item.label] = True
            health_bucket = credential_health.setdefault(item.provider, {})
            try:
                self.crypto_service.decrypt(item.encrypted_value)
            except ValueError:
                health_bucket[item.label] = "unreadable"
            else:
                health_bucket[item.label] = (
                    "healthy" if item.provider in {"openai", "google"} else "stored"
                )
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
            credential_health=credential_health,
        )

    def get_ollama_url(self) -> str:
        record = self.settings_repo.get_or_create()
        return record.ollama_url

    def update_settings(self, payload: ModelSettingsUpdateRequest) -> ModelSettingsResponse:
        for provider, labels in payload.credentials.items():
            for label, raw_value in labels.items():
                if not raw_value.strip():
                    self.credentials_repo.deactivate(provider=provider, label=label)
                    continue
                encrypted = self.crypto_service.encrypt(raw_value.strip())
                self.credentials_repo.upsert(
                    provider=provider,
                    label=label,
                    encrypted_value=encrypted.value,
                    key_version=encrypted.key_version,
                )
        self.settings_repo.update(
            active_provider_mode=payload.active_provider_mode or DEFAULT_MODEL_PROVIDER_MODE,
            chat_model_provider=payload.chat_model_provider or DEFAULT_MODEL_PROVIDER,
            chat_model_name=payload.chat_model_name or DEFAULT_MODEL_NAME,
            parser_model_provider=payload.parser_model_provider or DEFAULT_MODEL_PROVIDER,
            parser_model_name=payload.parser_model_name or DEFAULT_MODEL_NAME,
            agent_model_provider=payload.agent_model_provider or DEFAULT_MODEL_PROVIDER,
            agent_model_name=payload.agent_model_name or DEFAULT_MODEL_NAME,
            ollama_url=payload.ollama_url or OLLAMA_DEFAULT_HOST,
            openai_base_url=payload.openai_base_url or None,
            google_base_url=payload.google_base_url or None,
        )
        return self.get_settings()
