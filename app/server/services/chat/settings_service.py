from __future__ import annotations

from typing import cast

from server.common.typing import is_json_object, json_array

from server.contracts.chat import (
    ModelProviderMode,
    ModelSettingsResponse,
    ModelSettingsUpdateRequest,
)
from server.repositories.credentials import CredentialRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.chat.model_library import (
    ChatModelLibraryService,
    DYNAMIC_CLOUD_PROVIDERS,
    ModelLibrarySourceError,
)
from server.services.cryptography import CredentialEncryptionService
from server.services.llm.context_budget import resolve_model_context_profile
from server.services.llm.context_profile_resolver import ModelContextProfileResolver


###############################################################################
class ChatSettingsValidationError(ValueError):
    pass


###############################################################################
class ChatSettingsService:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        settings_repo: ModelSettingsRepository,
        credentials_repo: CredentialRepository,
        crypto_service: CredentialEncryptionService,
        model_library_service: ChatModelLibraryService,
        context_profile_resolver: ModelContextProfileResolver | None = None,
    ) -> None:
        self.settings_repo = settings_repo
        self.credentials_repo = credentials_repo
        self.crypto_service = crypto_service
        self.model_library_service = model_library_service
        self.context_profile_resolver = context_profile_resolver

    # -------------------------------------------------------------------------
    def get_settings(self) -> ModelSettingsResponse:
        record = self.settings_repo.get_required()
        if record.active_provider_mode not in {"local", "cloud"}:
            raise ChatSettingsValidationError(
                "Stored model settings contain an invalid provider mode."
            )
        active_provider_mode: ModelProviderMode = cast(
            ModelProviderMode, record.active_provider_mode
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
                    "healthy"
                    if item.provider in {"openai", "google", *DYNAMIC_CLOUD_PROVIDERS}
                    else "stored"
                )
        profile = (
            self.context_profile_resolver.resolve(
                record.agent_model_provider,
                record.agent_model_name,
            )
            if self.context_profile_resolver is not None
            else resolve_model_context_profile(
                record.agent_model_provider,
                record.agent_model_name,
            )
        )
        selected_model_context = {
            "provider": record.agent_model_provider,
            "model": record.agent_model_name,
            "context_window_tokens": None,
            "maximum_output_tokens": None,
            "context_profile_source": "unknown",
        }
        if profile is not None:
            selected_model_context.update(
                {
                    "context_window_tokens": profile.context_window_tokens,
                    "maximum_output_tokens": profile.maximum_output_tokens,
                    "context_profile_source": profile.metadata_source,
                }
            )
        return ModelSettingsResponse(
            active_provider_mode=active_provider_mode,
            agent_model_provider=record.agent_model_provider,
            agent_model_name=record.agent_model_name,
            ollama_url=self.model_library_service.normalize_ollama_url(
                record.ollama_url
            ),
            openai_base_url=record.openai_base_url,
            google_base_url=record.google_base_url,
            deepseek_base_url=record.deepseek_base_url,
            credentials=credential_presence,
            credential_health=credential_health,
            selected_model_context=selected_model_context,
        )

    # -------------------------------------------------------------------------
    def get_ollama_url(self) -> str:
        record = self.settings_repo.get_required()
        return self.model_library_service.normalize_ollama_url(record.ollama_url)

    # -------------------------------------------------------------------------
    def update_settings(
        self, payload: ModelSettingsUpdateRequest
    ) -> ModelSettingsResponse:
        current = self.get_settings()
        should_validate_model_selection = any(
            value is not None
            for value in (
                payload.active_provider_mode,
                payload.agent_model_provider,
                payload.agent_model_name,
                payload.ollama_url,
            )
        )
        next_active_provider_mode = (
            payload.active_provider_mode
            if payload.active_provider_mode is not None
            else current.active_provider_mode
        )
        next_agent_model_provider = (
            payload.agent_model_provider
            if payload.agent_model_provider is not None
            else current.agent_model_provider
        )
        next_agent_model_name = (
            payload.agent_model_name
            if payload.agent_model_name is not None
            else current.agent_model_name
        )
        next_ollama_url = self.model_library_service.normalize_ollama_url(
            payload.ollama_url if payload.ollama_url is not None else current.ollama_url
        )
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
        next_deepseek_base_url = (
            None
            if payload.deepseek_base_url == ""
            else payload.deepseek_base_url
            if payload.deepseek_base_url is not None
            else current.deepseek_base_url
        )
        has_agent_assignment = bool(
            next_agent_model_provider.strip() and next_agent_model_name.strip()
        )
        if has_agent_assignment or should_validate_model_selection:
            self._validate_agent_assignment(
                agent_model_provider=next_agent_model_provider,
                agent_model_name=next_agent_model_name,
            )
        if should_validate_model_selection and has_agent_assignment:
            self._validate_local_model_selection(
                agent_model_provider=next_agent_model_provider,
                agent_model_name=next_agent_model_name,
                ollama_url=next_ollama_url,
            )
            self._validate_agent_capabilities(
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
                    key_version=cast(int, encrypted.key_version),
                )
        self.settings_repo.update(
            active_provider_mode=next_active_provider_mode,
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
            ollama_url=next_ollama_url,
            openai_base_url=next_openai_base_url,
            google_base_url=next_google_base_url,
            deepseek_base_url=next_deepseek_base_url,
        )
        return self.get_settings()

    # -------------------------------------------------------------------------
    def _validate_local_model_selection(
        self,
        *,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
    ) -> None:
        if agent_model_provider != "ollama" or not agent_model_name:
            return
        local_models = {
            str(item.get("id", ""))
            for item in json_array(
                self.model_library_service.list_models(ollama_url=ollama_url).get(
                    "local"
                )
            )
            if is_json_object(item)
        }
        if agent_model_name not in local_models:
            raise ChatSettingsValidationError(
                "Selected agent model is not available from Ollama."
            )

    # -------------------------------------------------------------------------
    def _validate_agent_capabilities(
        self,
        *,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
    ) -> None:
        try:
            agent_model = self.model_library_service.find_model(
                provider=agent_model_provider,
                model_name=agent_model_name,
                ollama_url=ollama_url,
                require_provider_availability=True,
            )
        except ModelLibrarySourceError:
            # A provider catalog outage must not turn missing capability
            # metadata into an explicit capability rejection.  The selected
            # model remains executable; the first request is authoritative.
            return
        if agent_model is not None and agent_model.get("supports_tools") is False:
            raise ChatSettingsValidationError(
                "Selected agent model does not support native tool calling."
            )
        if (
            agent_model is not None
            and agent_model.get("supports_structured_output") is False
        ):
            raise ChatSettingsValidationError(
                "Selected agent model does not support structured output."
            )
        if (
            agent_model is None
            and agent_model_provider in DYNAMIC_CLOUD_PROVIDERS
            and agent_model_name
        ):
            raise ChatSettingsValidationError(
                f"Selected {agent_model_provider} agent model could not be found in the live provider catalog."
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _validate_agent_assignment(
        *,
        agent_model_provider: str,
        agent_model_name: str,
    ) -> None:
        if not agent_model_provider.strip() or not agent_model_name.strip():
            raise ChatSettingsValidationError(
                "Agent model provider and model name must both be configured."
            )
