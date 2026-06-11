from __future__ import annotations

from typing import Any

from server.repositories.credentials import CredentialRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.cryptography import CredentialEncryptionService
from server.services.llm.base import LLMProvider
from server.services.llm.deepseek_provider import DeepSeekProvider
from server.services.llm.errors import LLMConfigurationError
from server.services.llm.google_provider import GoogleProvider
from server.services.llm.ollama import OllamaProvider
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.openai_provider import OpenAIProvider
from server.services.llm.types import LLMRequest

###############################################################################
class LLMFactory:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository | None = None,
        credentials_repo: CredentialRepository | None = None,
        crypto_service: CredentialEncryptionService | None = None,
        ollama_tool_capability_cache: OllamaToolCapabilityCache | None = None,
    ) -> None:
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.credentials_repo = credentials_repo or CredentialRepository()
        self.crypto_service = crypto_service or CredentialEncryptionService()
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )

    # -------------------------------------------------------------------------
    def _resolve_provider_api_key(self, provider: str) -> str:
        credential = self.credentials_repo.get_active(provider=provider, label="api_key")
        if credential is None:
            if provider == "openai":
                raise LLMConfigurationError(
                    "OpenAI credentials are not configured. Add an OpenAI API key in Settings."
                )
            if provider == "deepseek":
                raise LLMConfigurationError(
                    "DeepSeek credentials are not configured. Add a DeepSeek API key in Settings."
                )
            raise LLMConfigurationError(
                "Google credentials are not configured. Add a Google/Gemini API key in Settings."
            )
        try:
            api_key = self.crypto_service.decrypt(credential.encrypted_value)
        except ValueError as exc:
            provider_label = (
                "OpenAI"
                if provider == "openai"
                else "DeepSeek"
                if provider == "deepseek"
                else "Google"
            )
            raise LLMConfigurationError(
                f"{provider_label} credentials are saved but cannot be decrypted. Re-enter the API key in Settings."
            ) from exc
        self.credentials_repo.mark_used(provider=provider, label="api_key")
        return api_key

    # -------------------------------------------------------------------------
    def get_provider(self, provider: str) -> LLMProvider:
        normalized = provider.strip().lower()
        settings = self.settings_repo.get_or_create()
        if normalized == "ollama":
            return OllamaProvider(
                base_url=settings.ollama_url,
                tool_capability_cache=self.ollama_tool_capability_cache,
            )
        if normalized == "openai":
            api_key = self._resolve_provider_api_key("openai")
            return OpenAIProvider(api_key=api_key, base_url=settings.openai_base_url)
        if normalized == "google":
            api_key = self._resolve_provider_api_key("google")
            return GoogleProvider(api_key=api_key, base_url=settings.google_base_url)
        if normalized == "deepseek":
            api_key = self._resolve_provider_api_key("deepseek")
            return DeepSeekProvider(
                api_key=api_key,
                base_url=settings.deepseek_base_url,
            )
        raise ValueError(f"Unsupported model provider '{provider}'.")

    # -------------------------------------------------------------------------
    def get_chat_provider(self, provider: str) -> LLMProvider:
        return _ChatOnlyProvider(self.get_provider(provider))

###############################################################################
class _ChatOnlyProvider:

    # -------------------------------------------------------------------------
    def __init__(self, delegate: LLMProvider) -> None:
        self._delegate = delegate
        self.provider_name = getattr(delegate, "provider_name", "chat")

    # -------------------------------------------------------------------------
    def __getattr__(self, item: str):  # noqa: ANN001
        return getattr(self._delegate, item)

    # -------------------------------------------------------------------------
    def structured_output(
        self, request: LLMRequest, schema: type[object]
    ) -> dict[str, Any]:
        raise RuntimeError("Structured extraction is forbidden on chat-model path.")
