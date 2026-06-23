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
        record = self._repair_incomplete_assignments(record)
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
            chat_model_provider=record.chat_model_provider,
            chat_model_name=record.chat_model_name,
            parser_model_provider=record.parser_model_provider,
            parser_model_name=record.parser_model_name,
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
                payload.chat_model_provider,
                payload.chat_model_name,
                payload.parser_model_provider,
                payload.parser_model_name,
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
        next_chat_model_provider = (
            payload.chat_model_provider
            if payload.chat_model_provider is not None
            else current.chat_model_provider
        )
        next_chat_model_name = (
            payload.chat_model_name
            if payload.chat_model_name is not None
            else current.chat_model_name
        )
        next_parser_model_provider = (
            payload.parser_model_provider
            if payload.parser_model_provider is not None
            else current.parser_model_provider
        )
        next_parser_model_name = (
            payload.parser_model_name
            if payload.parser_model_name is not None
            else current.parser_model_name
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
        self._validate_role_assignments(
            chat_model_provider=next_chat_model_provider,
            chat_model_name=next_chat_model_name,
            parser_model_provider=next_parser_model_provider,
            parser_model_name=next_parser_model_name,
            agent_model_provider=next_agent_model_provider,
            agent_model_name=next_agent_model_name,
        )
        if should_validate_model_selection:
            changed_roles = self._changed_roles(payload)
            self._validate_local_model_selection(
                chat_model_provider=next_chat_model_provider,
                chat_model_name=next_chat_model_name,
                parser_model_provider=next_parser_model_provider,
                parser_model_name=next_parser_model_name,
                agent_model_provider=next_agent_model_provider,
                agent_model_name=next_agent_model_name,
                ollama_url=next_ollama_url,
                changed_roles=changed_roles,
                validate_all_local_roles=payload.ollama_url is not None,
            )
            self._validate_role_capabilities(
                parser_model_provider=next_parser_model_provider,
                parser_model_name=next_parser_model_name,
                agent_model_provider=next_agent_model_provider,
                agent_model_name=next_agent_model_name,
                ollama_url=next_ollama_url,
                changed_roles=changed_roles,
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
            deepseek_base_url=next_deepseek_base_url,
        )
        return self.get_settings()

    # -------------------------------------------------------------------------
    def _repair_incomplete_assignments(self, record):
        assignments = self._normalized_assignments(record)
        incomplete_roles = {
            role
            for role, values in assignments.items()
            if not values["provider"] or not values["model"]
        }
        if not incomplete_roles:
            return record

        available_models = self._available_models(
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url)
        )
        repaired_assignments = {
            role: dict(values) for role, values in assignments.items()
        }
        for role in sorted(incomplete_roles):
            repaired_assignments[role] = self._repair_role_assignment(
                role=role,
                current_provider=repaired_assignments[role]["provider"],
                current_model=repaired_assignments[role]["model"],
                active_provider_mode=str(getattr(record, "active_provider_mode", "") or ""),
                available_models=available_models,
            )

        self._validate_role_assignments(
            chat_model_provider=repaired_assignments["chat"]["provider"],
            chat_model_name=repaired_assignments["chat"]["model"],
            parser_model_provider=repaired_assignments["parser"]["provider"],
            parser_model_name=repaired_assignments["parser"]["model"],
            agent_model_provider=repaired_assignments["agent"]["provider"],
            agent_model_name=repaired_assignments["agent"]["model"],
        )
        self._validate_local_model_selection(
            chat_model_provider=repaired_assignments["chat"]["provider"],
            chat_model_name=repaired_assignments["chat"]["model"],
            parser_model_provider=repaired_assignments["parser"]["provider"],
            parser_model_name=repaired_assignments["parser"]["model"],
            agent_model_provider=repaired_assignments["agent"]["provider"],
            agent_model_name=repaired_assignments["agent"]["model"],
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url),
            changed_roles={"chat", "parser", "agent"},
            validate_all_local_roles=True,
        )
        self._validate_role_capabilities(
            parser_model_provider=repaired_assignments["parser"]["provider"],
            parser_model_name=repaired_assignments["parser"]["model"],
            agent_model_provider=repaired_assignments["agent"]["provider"],
            agent_model_name=repaired_assignments["agent"]["model"],
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url),
            changed_roles={"parser", "agent"},
        )
        return self.settings_repo.update(
            active_provider_mode=(
                record.active_provider_mode
                if record.active_provider_mode in {"local", "cloud"}
                else DEFAULT_MODEL_PROVIDER_MODE
            ),
            chat_model_provider=repaired_assignments["chat"]["provider"],
            chat_model_name=repaired_assignments["chat"]["model"],
            parser_model_provider=repaired_assignments["parser"]["provider"],
            parser_model_name=repaired_assignments["parser"]["model"],
            agent_model_provider=repaired_assignments["agent"]["provider"],
            agent_model_name=repaired_assignments["agent"]["model"],
            ollama_url=self.model_library_service.normalize_ollama_url(record.ollama_url),
            openai_base_url=record.openai_base_url,
            google_base_url=record.google_base_url,
            deepseek_base_url=record.deepseek_base_url,
        )

    # -------------------------------------------------------------------------
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
        changed_roles: set[str],
        validate_all_local_roles: bool = False,
    ) -> None:
        assignments = (
            ("chat", chat_model_provider, chat_model_name),
            ("parser", parser_model_provider, parser_model_name),
            ("agent", agent_model_provider, agent_model_name),
        )
        requested_local_models = {
            model_name
            for _, provider, model_name in assignments
            if provider == "ollama"
            and model_name
            and (validate_all_local_roles or _ in changed_roles)
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
        if (
            (validate_all_local_roles or "chat" in changed_roles)
            and chat_model_provider == "ollama"
            and chat_model_name in unavailable
        ):
            raise ChatSettingsValidationError(
                "Selected chat model is not available from Ollama."
            )
        if (
            (validate_all_local_roles or "parser" in changed_roles)
            and parser_model_provider == "ollama"
            and parser_model_name in unavailable
        ):
            raise ChatSettingsValidationError(
                "Selected parser model is not available from Ollama."
            )
        if (
            (validate_all_local_roles or "agent" in changed_roles)
            and agent_model_provider == "ollama"
            and agent_model_name in unavailable
        ):
            raise ChatSettingsValidationError(
                "Selected agent model is not available from Ollama."
            )

    # -------------------------------------------------------------------------
    def _validate_role_capabilities(
        self,
        *,
        parser_model_provider: str,
        parser_model_name: str,
        agent_model_provider: str,
        agent_model_name: str,
        ollama_url: str,
        changed_roles: set[str],
    ) -> None:
        if "agent" in changed_roles:
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
            if agent_model is None and agent_model_provider == "deepseek" and agent_model_name:
                raise ChatSettingsValidationError(
                    "Selected DeepSeek agent model could not be found in the live DeepSeek catalog."
                )
        if "parser" in changed_roles:
            try:
                parser_model = self.model_library_service.find_model(
                    provider=parser_model_provider,
                    model_name=parser_model_name,
                    ollama_url=ollama_url,
                    require_provider_availability=True,
                )
            except ModelLibrarySourceError as exc:
                raise ChatSettingsValidationError(
                    f"Could not validate DeepSeek model selection: {exc}"
                ) from exc
            if parser_model is not None and not bool(
                parser_model.get("supports_structured_output")
            ):
                raise ChatSettingsValidationError(
                    "Selected parser model does not support structured output."
                )
            if parser_model is None and parser_model_provider == "deepseek" and parser_model_name:
                raise ChatSettingsValidationError(
                    "Selected DeepSeek parser model could not be found in the live DeepSeek catalog."
                )

    # -------------------------------------------------------------------------
    @staticmethod
    def _normalized_assignments(record: object) -> dict[str, dict[str, str]]:
        return {
            "chat": {
                "provider": str(getattr(record, "chat_model_provider", "") or "").strip(),
                "model": str(getattr(record, "chat_model_name", "") or "").strip(),
            },
            "parser": {
                "provider": str(getattr(record, "parser_model_provider", "") or "").strip(),
                "model": str(getattr(record, "parser_model_name", "") or "").strip(),
            },
            "agent": {
                "provider": str(getattr(record, "agent_model_provider", "") or "").strip(),
                "model": str(getattr(record, "agent_model_name", "") or "").strip(),
            },
        }

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
    def _repair_role_assignment(
        self,
        *,
        role: str,
        current_provider: str,
        current_model: str,
        active_provider_mode: str,
        available_models: dict[str, list[dict[str, object]]],
    ) -> dict[str, str]:
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
            assignment = self._select_assignment_for_role(
                role=role,
                provider=provider,
                current_model=current_model,
                models=available_models.get(provider, []),
            )
            if assignment is not None:
                return assignment
        raise ChatSettingsValidationError(
            f"No valid configured model assignment is available for the {role} role."
        )

    # -------------------------------------------------------------------------
    def _select_assignment_for_role(
        self,
        *,
        role: str,
        provider: str,
        current_model: str,
        models: list[dict[str, object]],
    ) -> dict[str, str] | None:
        if not models:
            return None
        preferred_models = [current_model] if current_model else []
        preferred_models.extend(
            {
                ("openai", "chat"): ["gpt-4.1-mini", "gpt-5-mini"],
                ("openai", "parser"): ["gpt-4.1-mini", "gpt-5-mini"],
                ("openai", "agent"): ["gpt-4.1", "gpt-5-mini"],
                ("google", "chat"): ["gemini-2.5-flash", "gemini-2.0-flash"],
                ("google", "parser"): ["gemini-2.5-flash", "gemini-2.0-flash"],
                ("google", "agent"): ["gemini-2.5-pro", "gemini-2.5-flash"],
                ("deepseek", "chat"): ["deepseek-chat", "deepseek-reasoner"],
                ("deepseek", "parser"): ["deepseek-chat", "deepseek-reasoner"],
                ("deepseek", "agent"): ["deepseek-chat", "deepseek-reasoner"],
            }.get((provider, role), [])
        )
        candidates = [
            item
            for item in models
            if self._role_requirements_met(role=role, model=item)
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
    def _role_requirements_met(*, role: str, model: dict[str, object]) -> bool:
        if role == "agent":
            return bool(model.get("supports_tools"))
        if role == "parser":
            return bool(model.get("supports_structured_output"))
        return True

    # -------------------------------------------------------------------------
    @staticmethod
    def _validate_role_assignments(
        *,
        chat_model_provider: str,
        chat_model_name: str,
        parser_model_provider: str,
        parser_model_name: str,
        agent_model_provider: str,
        agent_model_name: str,
    ) -> None:
        assignments = (
            ("chat", chat_model_provider, chat_model_name),
            ("parser", parser_model_provider, parser_model_name),
            ("agent", agent_model_provider, agent_model_name),
        )
        for role, provider, model in assignments:
            normalized_provider = provider.strip()
            normalized_model = model.strip()
            if not normalized_provider or not normalized_model:
                raise ChatSettingsValidationError(
                    f"{role.capitalize()} model provider and model name must both be configured."
                )

    # -------------------------------------------------------------------------
    @staticmethod
    def _changed_roles(payload: ModelSettingsUpdateRequest) -> set[str]:
        changed_roles: set[str] = set()
        if payload.chat_model_provider is not None or payload.chat_model_name is not None:
            changed_roles.add("chat")
        if payload.parser_model_provider is not None or payload.parser_model_name is not None:
            changed_roles.add("parser")
        if payload.agent_model_provider is not None or payload.agent_model_name is not None:
            changed_roles.add("agent")
        return changed_roles


