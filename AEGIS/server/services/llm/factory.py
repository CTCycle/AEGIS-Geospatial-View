from __future__ import annotations

from AEGIS.server.repositories.credentials import CredentialRepository
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.cryptography import CredentialEncryptionService
from AEGIS.server.services.llm.base import LLMProvider
from AEGIS.server.services.llm.google_provider import GoogleProvider
from AEGIS.server.services.llm.ollama import OllamaProvider
from AEGIS.server.services.llm.openai_provider import OpenAIProvider


class LLMFactory:
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

    def get_provider(self, provider: str) -> LLMProvider:
        normalized = provider.strip().lower()
        settings = self.settings_repo.get_or_create()
        if normalized == "ollama":
            return OllamaProvider(base_url=settings.ollama_url)
        if normalized == "openai":
            credential = self.credentials_repo.get_active(provider="openai", label="api_key")
            if credential is None:
                raise ValueError("OpenAI credentials are not configured.")
            api_key = self.crypto_service.decrypt(credential.encrypted_value)
            return OpenAIProvider(api_key=api_key, base_url=settings.openai_base_url)
        if normalized == "google":
            credential = self.credentials_repo.get_active(provider="google", label="api_key")
            if credential is None:
                raise ValueError("Google credentials are not configured.")
            api_key = self.crypto_service.decrypt(credential.encrypted_value)
            return GoogleProvider(api_key=api_key, base_url=settings.google_base_url)
        raise ValueError(f"Unsupported model provider '{provider}'.")
