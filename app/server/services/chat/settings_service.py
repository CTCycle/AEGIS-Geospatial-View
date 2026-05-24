from __future__ import annotations

from server.common.constants import (
    DEFAULT_MODEL_PROVIDER_MODE,
)
from server.domain.chat import (
    ModelProviderMode,
    ModelSettingsResponse,
    ModelSettingsUpdateRequest,
)
from server.repositories.credentials import CredentialRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.cryptography import CredentialEncryptionService
from server.services.chat.model_library import ChatModelLibraryService


class ChatSettingsValidationError(ValueError):
    pass


class ChatSettingsService:
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository | None = None,
        credentials_repo: CredentialRepository | None = None,
        crypto_service: CredentialEncryptionService | None = None,
        model_library_service: ChatModelLibraryService | None = None,
    ) -> None:
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.credentials_repo = credentials_repo or CredentialRepository()
        self.crypto_service = crypto_service or CredentialEncryptionService()
        self.model_library_service = model_library_service or ChatModelLibraryService()

    def get_settings(self) -> ModelSettingsResponse:
        record = self.settings_repo.get_or_create()
        active_provider_mode: ModelProviderMode = (
            record.active_provider_mode
            if record.active_provider_mode in {"local", "cloud"}
            else DEFAULT_MODEL_PROVIDER_MODE
        )
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
            active_provider_mode=active_provider_mode,
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

    def update_settings(
        self, payload: ModelSettingsUpdateRequest
    ) -> ModelSettingsResponse:
        current = self.get_settings()
        next_active_provider_mode = (
            payload.active_provider_mode or current.active_provider_mode
        )
        next_chat_model_provider = (
            payload.chat_model_provider or current.chat_model_provider
        )
        next_chat_model_name = payload.chat_model_name or current.chat_model_name
        next_parser_model_provider = (
            payload.parser_model_provider or current.parser_model_provider
        )
        next_parser_model_name = payload.parser_model_name or current.parser_model_name
        next_agent_model_provider = (
            payload.agent_model_provider or current.agent_model_provider
        )
        next_agent_model_name = payload.agent_model_name or current.agent_model_name
        next_ollama_url = payload.ollama_url or current.ollama_url
        next_openai_base_url = (
            None
            if payload.openai_base_url == ""
            else payload.openai_base_url
            if payload.openai_base_url is not None
            else current.openai_base_url
        )
        next_google_base_url = (
            None
            if payload.google_base_url == ""
            else payload.google_base_url
            if payload.google_base_url is not None
            else current.google_base_url
        )
        self._validate_local_model_selection(
            chat_model_provider=next_chat_model_provider,
            chat_model_name=next_chat_model_name,
            parser_model_provider=next_parser_model_provider,
            parser_model_name=next_parser_model_name,
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
            ollama_url=next_ollama_url,
        )
        self._validate_role_capabilities(
            parser_model_provider=next_parser_model_provider,
            parser_model_name=next_parser_model_name,
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
            ollama_url=next_ollama_url,
        )
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
            active_provider_mode=next_active_provider_mode,
            chat_model_provider=next_chat_model_provider,
            chat_model_name=next_chat_model_name,
            parser_model_provider=next_parser_model_provider,
            parser_model_name=next_parser_model_name,
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
            ollama_url=next_ollama_url,
            openai_base_url=next_openai_base_url,
            google_base_url=next_google_base_url,
        )
        return self.get_settings()

    def _validate_local_model_selection(
        self,
        *,
        chat_model_provider: str,
        chat_model_name: str,
        parser_model_provider: str,
        parser_model_name: str,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
    ) -> None:
        assignments = (
            ("chat", chat_model_provider, chat_model_name),
            ("parser", parser_model_provider, parser_model_name),
            ("agent", agent_model_provider, agent_model_name),
        )
        requested_local_models = {
            model_name
            for _, provider, model_name in assignments
            if provider == "ollama" and model_name
        }
        if not requested_local_models:
            return
        local_models = {
            str(item.get("id", ""))
            for item in self.model_library_service.list_models(
                ollama_url=ollama_url
            ).get("local", [])
            if isinstance(item, dict)
        }
        unavailable = requested_local_models.difference(local_models)
        if chat_model_provider == "ollama" and chat_model_name in unavailable:
            raise ChatSettingsValidationError(
                "Selected chat model is not available from Ollama."
            )
        if unavailable:
            raise ChatSettingsValidationError(
                "Selected embedding model is not available from Ollama."
            )

    def _validate_role_capabilities(
        self,
        *,
        parser_model_provider: str,
        parser_model_name: str,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
    ) -> None:
        agent_model = self.model_library_service.find_model(
            provider=agent_model_provider,
            model_name=agent_model_name,
            ollama_url=ollama_url,
        )
        if agent_model is not None and not bool(agent_model.get("supports_tools")):
            raise ChatSettingsValidationError(
                "Selected agent model does not support native tool calling."
            )
        parser_model = self.model_library_service.find_model(
            provider=parser_model_provider,
            model_name=parser_model_name,
            ollama_url=ollama_url,
        )
        if parser_model is not None and not bool(
            parser_model.get("supports_structured_output")
        ):
            raise ChatSettingsValidationError(
                "Selected parser model does not support structured output."
            )
