from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Any

from server.repositories.model_settings import ModelSettingsRepository
from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.context_budget import resolve_model_context_profile
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

    def __init__(
        self,
        *,
        model_library_service: ChatModelLibraryService,
        settings_repo: ModelSettingsRepository,
        cache_ttl_seconds: float = 60.0,
    ) -> None:
        self.model_library_service = model_library_service
        self.settings_repo = settings_repo
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[tuple[str, str, str], _CachedProfile] = {}

    # -------------------------------------------------------------------------
    def resolve(self, provider: str, model: str) -> ModelContextProfile | None:
        normalized_provider = provider.strip().lower()
        normalized_model = model.strip()
        if not normalized_provider or not normalized_model:
            return None

        static_profile = resolve_model_context_profile(
            normalized_provider, normalized_model
        )
        if static_profile is not None:
            return static_profile

        ollama_url = self._ollama_url()
        cache_key = (normalized_provider, normalized_model, ollama_url)
        cached = self._cache.get(cache_key)
        now = monotonic()
        if cached is not None and cached.expires_at > now:
            return cached.profile

        profile: ModelContextProfile | None = None
        try:
            descriptor = self.model_library_service.find_model(
                provider=normalized_provider,
                model_name=normalized_model,
                ollama_url=ollama_url,
            )
        except Exception:
            descriptor = None
        if isinstance(descriptor, dict):
            metadata = self._descriptor_metadata(descriptor)
            profile = resolve_model_context_profile(
                normalized_provider,
                normalized_model,
                metadata=metadata,
            )

        self._cache[cache_key] = _CachedProfile(
            expires_at=now + self.cache_ttl_seconds,
            profile=profile,
        )
        return profile

    # -------------------------------------------------------------------------
    def request_metadata(self, provider: str, model: str) -> dict[str, Any]:
        profile = self.resolve(provider, model)
        if profile is None:
            return {}
        return {
            "context_window_tokens": profile.context_window_tokens,
            "maximum_output_tokens": profile.maximum_output_tokens,
            "default_output_reserve": profile.default_output_reserve,
            "tokenizer_strategy": profile.tokenizer_strategy,
            "supports_context_caching": profile.supports_context_caching,
            "supports_server_compaction": profile.supports_server_compaction,
            "context_profile_source": profile.metadata_source,
        }

    # -------------------------------------------------------------------------
    def _ollama_url(self) -> str:
        settings = self.settings_repo.get_required()
        return self.model_library_service.normalize_ollama_url(settings.ollama_url)

    # -------------------------------------------------------------------------
    @staticmethod
    def _descriptor_metadata(descriptor: dict[str, Any]) -> dict[str, Any]:
        metadata = descriptor.get("metadata")
        merged = dict(metadata) if isinstance(metadata, dict) else {}
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
        ):
            if descriptor.get(key) is not None and key not in merged:
                merged[key] = descriptor[key]
        return merged
