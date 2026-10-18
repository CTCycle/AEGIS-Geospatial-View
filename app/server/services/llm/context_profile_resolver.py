from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

from server.common.constants import OLLAMA_DEFAULT_HOST
from server.common.typing import is_json_object, json_object
from server.repositories.model_settings import ModelSettingsRepository
from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.context_budget import (
    normalize_model_context_profile,
    profile_to_request_metadata,
    resolve_model_context_profile,
)
from server.services.llm.opencode_provider import (
    DEFAULT_OPENCODE_BASE_URL,
    DEFAULT_OPENCODE_GO_BASE_URL,
)
from server.services.llm.deepseek_provider import DEFAULT_DEEPSEEK_BASE_URL
from server.services.llm.google_provider import DEFAULT_GOOGLE_BASE_URL
from server.services.llm.types import ModelContextProfile

###############################################################################
@dataclass(frozen=True)
class _CachedProfile:
    expires_at: float
    profile: ModelContextProfile | None

###############################################################################
class ModelContextProfileResolver:
    """Resolve one trusted profile for settings and provider requests.

    Exact static catalog records win.  Dynamic provider records are consulted
    only when the model is not in that catalog, and missing metadata remains
    unknown rather than becoming a model-name heuristic.
    """

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        model_library_service: ChatModelLibraryService,
        settings_repo: ModelSettingsRepository,
        cache_ttl_seconds: float = 600.0,
        negative_cache_ttl_seconds: float = 45.0,
    ) -> None:
        self.model_library_service = model_library_service
        self.settings_repo = settings_repo
        self.cache_ttl_seconds = cache_ttl_seconds
        self.negative_cache_ttl_seconds = negative_cache_ttl_seconds
        self._cache: dict[tuple[str, str, str], _CachedProfile] = {}
        self._configured_ollama_url = self._load_ollama_url_once()
        self._invalidation_revision = 0

    # -------------------------------------------------------------------------
    def resolve(self, provider: str, model: str) -> ModelContextProfile | None:
        normalized_provider = provider
        normalized_model = model.strip()
        if not normalized_provider or not normalized_model:
            return None

        static_profile = resolve_model_context_profile(
            normalized_provider, normalized_model
        )
        if static_profile is not None:
            return static_profile

        cache_key = self._cache_key(normalized_provider, normalized_model)
        cached = self._cache.get(cache_key)
        now = monotonic()
        if cached is not None and cached.expires_at > now:
            return cached.profile

        profile: ModelContextProfile | None = None
        try:
            descriptor = self.model_library_service.find_cached_model(
                provider=normalized_provider,
                model_name=normalized_model,
                ollama_url=self._ollama_url(),
            )
        except Exception:
            descriptor = None
        if isinstance(descriptor, dict):
            profile = self._profile_from_descriptor(
                normalized_provider,
                normalized_model,
                descriptor,
            )

        self._cache[cache_key] = _CachedProfile(
            expires_at=now
            + (
                self.cache_ttl_seconds
                if profile is not None
                else self.negative_cache_ttl_seconds
            ),
            profile=profile,
        )
        return profile

    # -------------------------------------------------------------------------
    def resolve_selected(self, provider: str, model: str) -> ModelContextProfile | None:
        """Refresh selected-model metadata without making selection fail."""

        normalized_provider = provider.strip()
        normalized_model = model.strip()
        if not normalized_provider or not normalized_model:
            return None

        static_profile = resolve_model_context_profile(
            normalized_provider, normalized_model
        )
        if static_profile is not None:
            return static_profile

        cache_key = self._cache_key(normalized_provider, normalized_model)
        now = monotonic()
        cached = self._cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            return cached.profile

        cached_descriptor = self._cached_descriptor(
            normalized_provider, normalized_model
        )
        if cached_descriptor is not None:
            profile = self._profile_from_descriptor(
                normalized_provider, normalized_model, cached_descriptor
            )
            if profile is not None:
                self._cache[cache_key] = _CachedProfile(
                    expires_at=now + self.cache_ttl_seconds,
                    profile=profile,
                )
                return profile

        previous_profile = cached.profile if cached is not None else None
        descriptor: dict[str, Any] | None = None
        try:
            refresh = getattr(
                self.model_library_service, "refresh_selected_model", None
            )
            if callable(refresh):
                refreshed: object = refresh(
                    provider=normalized_provider,
                    model_name=normalized_model,
                    ollama_url=self._ollama_url(),
                )
                descriptor = refreshed if is_json_object(refreshed) else None
            else:
                found: object = self.model_library_service.find_model(
                    provider=normalized_provider,
                    model_name=normalized_model,
                    ollama_url=self._ollama_url(),
                    include_probe_status=False,
                )
                descriptor = found if is_json_object(found) else None
        except TypeError:
            # Small test doubles and older adapters may not accept the optional
            # probe-status argument.  A selected lookup remains best effort.
            try:
                found = self.model_library_service.find_model(
                    provider=normalized_provider,
                    model_name=normalized_model,
                    ollama_url=self._ollama_url(),
                )
                descriptor = found if is_json_object(found) else None
            except Exception:
                descriptor = None
        except Exception:
            descriptor = None

        profile = self._profile_from_descriptor(
            normalized_provider, normalized_model, descriptor
        )
        if profile is None:
            profile = previous_profile
        self._cache[cache_key] = _CachedProfile(
            expires_at=now
            + (
                self.cache_ttl_seconds
                if profile is not None and descriptor is not None
                else self.negative_cache_ttl_seconds
            ),
            profile=profile,
        )
        return profile

    # -------------------------------------------------------------------------
    def refresh(self, provider: str, model: str) -> ModelContextProfile | None:
        """Compatibility-named alias for selected-model hydration."""

        return self.resolve_selected(provider, model)

    # -------------------------------------------------------------------------
    def request_metadata(self, provider: str, model: str) -> dict[str, Any]:
        profile = self.resolve(provider, model)
        if profile is None:
            return {}
        return profile_to_request_metadata(profile)

    # -------------------------------------------------------------------------
    def selected_request_metadata(self, provider: str, model: str) -> dict[str, Any]:
        profile = self.resolve_selected(provider, model)
        return profile_to_request_metadata(profile) if profile is not None else {}

    # -------------------------------------------------------------------------
    def invalidate(self) -> None:
        self._cache.clear()
        self._invalidation_revision += 1
        self._configured_ollama_url = self._load_ollama_url_once()

    # -------------------------------------------------------------------------
    def _cache_key(self, provider: str, model: str) -> tuple[str, str, str]:
        return (
            provider,
            model,
            "|".join(
                [
                    self._endpoint_for(provider),
                    self._ollama_url(),
                    str(self._invalidation_revision),
                ]
            ),
        )

    # -------------------------------------------------------------------------
    def _endpoint_for(self, provider: str) -> str:
        try:
            settings = self.settings_repo.get_required()
        except Exception:
            settings = None
        configured = {
            "openai": getattr(settings, "openai_base_url", None),
            "google": getattr(settings, "google_base_url", None),
            "deepseek": getattr(settings, "deepseek_base_url", None),
            "opencode": DEFAULT_OPENCODE_BASE_URL,
            "opencode-go": DEFAULT_OPENCODE_GO_BASE_URL,
            "ollama": self._ollama_url(),
        }.get(provider)
        if configured:
            return str(configured).rstrip("/")
        return {
            "google": DEFAULT_GOOGLE_BASE_URL,
            "deepseek": DEFAULT_DEEPSEEK_BASE_URL,
            "ollama": OLLAMA_DEFAULT_HOST,
        }.get(provider, "")

    # -------------------------------------------------------------------------
    def _cached_descriptor(
        self, provider: str, model: str
    ) -> dict[str, Any] | None:
        try:
            return self.model_library_service.find_cached_model(
                provider=provider,
                model_name=model,
                ollama_url=self._ollama_url(),
            )
        except Exception:
            return None

    # -------------------------------------------------------------------------
    def _profile_from_descriptor(
        self, provider: str, model: str, descriptor: dict[str, Any] | None
    ) -> ModelContextProfile | None:
        if not isinstance(descriptor, dict):
            return None
        metadata = self._descriptor_metadata(descriptor)
        return normalize_model_context_profile(
            provider,
            model,
            metadata=metadata,
            default_metadata_source="provider_metadata",
            default_metadata_authority="provider",
        )

    # -------------------------------------------------------------------------
    def _ollama_url(self) -> str:
        return self._configured_ollama_url

    # -------------------------------------------------------------------------
    def _load_ollama_url_once(self) -> str:
        try:
            settings = self.settings_repo.get_required()
            return self.model_library_service.normalize_ollama_url(settings.ollama_url)
        except Exception:
            return self.model_library_service.normalize_ollama_url("")

    # -------------------------------------------------------------------------
    @staticmethod
    def _descriptor_metadata(descriptor: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = dict(json_object(descriptor.get("metadata")))
        for key in (
            "context_window_tokens",
            "context_length",
            "context_window",
            "max_context_tokens",
            "maximum_output_tokens",
            "max_output_tokens",
            "max_completion_tokens",
            "default_output_reserve",
            "tokenizer_strategy",
            "supports_context_caching",
            "supports_server_compaction",
            "context_profile_source",
            "context_metadata_authority",
            "metadata_authority",
        ):
            if descriptor.get(key) is not None and key not in merged:
                merged[key] = descriptor[key]
        return merged
