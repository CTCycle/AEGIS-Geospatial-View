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
from server.services.chat.model_library import (
    ChatModelLibraryService,
    ModelLibrarySourceError,
)
from server.services.cryptography import CredentialEncryptionService

###############################################################################
class ChatSettingsValidationError(ValueError):
    pass

###############################################################################
class ChatSettingsService:

    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    def get_settings(self) -> ModelSettingsResponse:
        record = self.settings_repo.get_or_create()
        record = self._repair_incomplete_agent_assignment(record)
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
                    "healthy"
                    if item.provider in {"openai", "google", "deepseek"}
                    else "stored"
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
        )

    # -------------------------------------------------------------------------
    def get_ollama_url(self) -> str:
        record = self.settings_repo.get_or_create()
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
            payload.ollama_url
            if payload.ollama_url is not None
            else current.ollama_url
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
        self._validate_agent_assignment(
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
        )
        if should_validate_model_selection:
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
                    key_version=encrypted.key_version,
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
    def _available_models(self, *, ollama_url: str) -> dict[str, list[dict[str, object]]]:
        available: dict[str, list[dict[str, object]]] = {}
        library = self.model_library_service.list_models(
            ollama_url=ollama_url,
            cloud_provider="deepseek",
        )
        active_credentials = self.credentials_repo.list_active()
        configured_cloud_providers: set[str] = set()
        for item in active_credentials:
            if item.label != "api_key":
                continue
            try:
                self.crypto_service.decrypt(item.encrypted_value)
            except ValueError:
                continue
            configured_cloud_providers.add(item.provider)
        for entry in library.get("cloud", []):
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("provider") or "").strip()
            if provider not in configured_cloud_providers:
                continue
            available.setdefault(provider, []).append(entry)
        local_models = [
            item
            for item in library.get("local", [])
            if isinstance(item, dict)
        ]
        if local_models:
            available["ollama"] = local_models
        return available

    # -------------------------------------------------------------------------
    def _repair_incomplete_agent_assignment(self, record):
        assignment = self._normalized_agent_assignment(record)
        if assignment["provider"] and assignment["model"]:
            return record

        available_models = self._available_models(
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url)
        )
        repaired = self._select_agent_assignment(
            current_provider=assignment["provider"],
            current_model=assignment["model"],
            active_provider_mode=str(getattr(record, "active_provider_mode", "") or ""),
            available_models=available_models,
        )
        if repaired is None:
            return record
        self._validate_agent_assignment(
            agent_model_provider=repaired["provider"],
            agent_model_name=repaired["model"],
        )
        self._validate_local_model_selection(
            agent_model_provider=repaired["provider"],
            agent_model_name=repaired["model"],
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url),
        )
        self._validate_agent_capabilities(
            agent_model_provider=repaired["provider"],
            agent_model_name=repaired["model"],
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url),
        )
        return self._persist_agent_assignment(
            record,
            provider=repaired["provider"],
            model=repaired["model"],
        )

    # -------------------------------------------------------------------------
    def _persist_agent_assignment(
        self,
        record: object,
        *,
        provider: str,
        model: str,
    ):
        return self.settings_repo.update(
            active_provider_mode=(
                getattr(record, "active_provider_mode", "")
                if getattr(record, "active_provider_mode", "") in {"local", "cloud"}
                else DEFAULT_MODEL_PROVIDER_MODE
            ),
            agent_model_provider=provider,
            agent_model_name=model,
            ollama_url=self.model_library_service.normalize_ollama_url(
                str(getattr(record, "ollama_url", ""))
            ),
            openai_base_url=getattr(record, "openai_base_url", None),
            google_base_url=getattr(record, "google_base_url", None),
            deepseek_base_url=getattr(record, "deepseek_base_url", None),
        )

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
            for item in self.model_library_service.list_models(
                ollama_url=ollama_url
            ).get("local", [])
            if isinstance(item, dict)
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
        except ModelLibrarySourceError as exc:
            raise ChatSettingsValidationError(
                f"Could not validate DeepSeek model selection: {exc}"
            ) from exc
        if agent_model is not None and not bool(agent_model.get("supports_tools")):
            raise ChatSettingsValidationError(
                "Selected agent model does not support native tool calling."
            )
        if agent_model is not None and not bool(
            agent_model.get("supports_structured_output")
        ):
            raise ChatSettingsValidationError(
                "Selected agent model does not support structured output."
            )
        if agent_model is None and agent_model_provider == "deepseek" and agent_model_name:
            raise ChatSettingsValidationError(
                "Selected DeepSeek agent model could not be found in the live DeepSeek catalog."
            )

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalized_agent_assignment(record: object) -> dict[str, str]:
        return {
            "provider": str(getattr(record, "agent_model_provider", "") or "").strip(),
            "model": str(getattr(record, "agent_model_name", "") or "").strip(),
        }

    # -------------------------------------------------------------------------
    def _select_agent_assignment(
        self,
        *,
        current_provider: str,
        current_model: str,
        active_provider_mode: str,
        available_models: dict[str, list[dict[str, object]]],
    ) -> dict[str, str] | None:
        provider_preferences: list[str] = []
        if current_provider:
            provider_preferences.append(current_provider)
        if active_provider_mode == "local":
            provider_preferences.append("ollama")
        provider_preferences.extend(["deepseek", "openai", "google", "ollama"])

        seen: set[str] = set()
        deduped_providers = [
            provider
            for provider in provider_preferences
            if provider not in seen and not seen.add(provider)
        ]
        for provider in deduped_providers:
            assignment = self._select_agent_model(
                provider=provider,
                current_model=current_model,
                models=available_models.get(provider, []),
            )
            if assignment is not None:
                return assignment
        return None

    # -------------------------------------------------------------------------
    def _select_agent_model(
        self,
        *,
        provider: str,
        current_model: str,
        models: list[dict[str, object]],
    ) -> dict[str, str] | None:
        if not models:
            return None
        preferred_models = [current_model] if current_model else []
        preferred_models.extend(
            {
                "openai": ["gpt-4.1", "gpt-5-mini", "gpt-4.1-mini"],
                "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
                "deepseek": ["deepseek-chat", "deepseek-reasoner"],
            }.get(provider, [])
        )
        candidates = [
            item
            for item in models
            if self._agent_requirements_met(model=item)
        ]
        if not candidates:
            return None
        by_name = {
            str(item.get("name") or item.get("id") or "").strip(): item
            for item in candidates
        }
        for name in preferred_models:
            normalized_name = str(name or "").strip()
            if normalized_name and normalized_name in by_name:
                return {"provider": provider, "model": normalized_name}
        fallback_name = str(
            candidates[0].get("name") or candidates[0].get("id") or ""
        ).strip()
        return {"provider": provider, "model": fallback_name} if fallback_name else None

    # -------------------------------------------------------------------------
    @staticmethod
    def _agent_requirements_met(*, model: dict[str, object]) -> bool:
        return bool(model.get("supports_tools")) and bool(
            model.get("supports_structured_output")
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


