from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from dataclasses import dataclass
from time import monotonic
from threading import Lock
from typing import cast
from server.common.constants import OLLAMA_DEFAULT_HOST
from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama import OllamaProvider
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.opencode_provider import (
    OPENCODE_GO_PROVIDER,
    OPENCODE_PROVIDER,
)
from server.services.llm.context_budget import resolve_model_context_profile
from server.services.llm.types import ModelDescriptor

###############################################################################
@dataclass
class _CachedOllamaFailure:
    expires_at: float
    message: str

###############################################################################
@dataclass
class _CachedModelDescriptors:
    expires_at: float
    models: list[ModelDescriptor]
    source: dict[str, object]

###############################################################################
class ModelLibrarySourceError(RuntimeError):
    pass


DYNAMIC_CLOUD_PROVIDERS = ("deepseek", OPENCODE_PROVIDER, OPENCODE_GO_PROVIDER)

###############################################################################
class ChatModelLibraryService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        ollama_tool_capability_cache: OllamaToolCapabilityCache | None = None,
        provider_factory: LLMFactory,
        ollama_unavailable_ttl_s: float = 20.0,
        dynamic_catalog_ttl_s: float = 900.0,
        dynamic_catalog_failure_ttl_s: float = 60.0,
    ) -> None:
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )
        self.provider_factory = provider_factory
        self.ollama_unavailable_ttl_s = ollama_unavailable_ttl_s
        self.dynamic_catalog_ttl_s = dynamic_catalog_ttl_s
        self.dynamic_catalog_failure_ttl_s = dynamic_catalog_failure_ttl_s
        self._ollama_unavailable_cache: dict[str, _CachedOllamaFailure] = {}
        self._dynamic_catalog_cache: dict[str, _CachedModelDescriptors] = {}
        self._ollama_model_cache: dict[str, _CachedModelDescriptors] = {}
        self._catalog_lock = Lock()
        self.structured_probe_service: object | None = None

    # -------------------------------------------------------------------------
    def set_structured_probe_service(self, service: object) -> None:
        self.structured_probe_service = service

    # -------------------------------------------------------------------------
    def invalidate_dynamic_catalogs(self) -> None:
        """Drop provider metadata after settings or credentials change."""

        with self._catalog_lock:
            self._dynamic_catalog_cache.clear()
            self._ollama_model_cache.clear()
            self._ollama_unavailable_cache.clear()

    # -------------------------------------------------------------------------
    def _structured_probe_status(self, provider: str) -> dict[str, object]:
        service = self.structured_probe_service
        latest = getattr(service, "latest", None) if service is not None else None
        if not callable(latest):
            return {
                "structured_probe_status": "not_tested",
                "structured_probe_checked_at": None,
                "structured_probe_expires_at": None,
            }
        try:
            result = latest()
        except Exception:
            return {
                "structured_probe_status": "not_tested",
                "structured_probe_checked_at": None,
                "structured_probe_expires_at": None,
            }
        if getattr(result, "provider", None) != provider:
            return {
                "structured_probe_status": "not_tested",
                "structured_probe_checked_at": None,
                "structured_probe_expires_at": None,
            }
        return {
            "structured_probe_status": str(
                getattr(result, "status", "not_tested")
            ),
            "structured_probe_checked_at": getattr(result, "checked_at", None),
            "structured_probe_expires_at": getattr(result, "expires_at", None),
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def model_payload(item: ModelDescriptor) -> dict[str, object]:
        capabilities = list(item.capabilities)
        metadata = dict(item.metadata)
        supports_tools = ChatModelLibraryService._capability_state(
            metadata,
            capabilities,
            "supports_tools",
            ("tools",),
        )
        supports_structured_output = ChatModelLibraryService._capability_state(
            metadata,
            capabilities,
            "supports_structured_output",
            ("structured", "structured_output"),
        )
        supports_vision = ChatModelLibraryService._capability_state(
            metadata,
            capabilities,
            "supports_vision",
            ("vision",),
        )
        supports_embeddings = ChatModelLibraryService._capability_state(
            metadata,
            capabilities,
            "supports_embeddings",
            ("embeddings",),
        )
        tool_support_source = str(
            metadata.get(
                "tool_support_source",
                "catalog"
                if item.provider in {"openai", "google"}
                else "provider"
                if item.provider in DYNAMIC_CLOUD_PROVIDERS
                else "unknown",
            )
        )
        profile = resolve_model_context_profile(
            item.provider,
            item.name,
            metadata=metadata,
        )
        context_window_tokens = ChatModelLibraryService._positive_int(
            metadata.get("context_window_tokens")
            or metadata.get("context_length")
            or metadata.get("context_window")
        ) or (profile.context_window_tokens if profile is not None else None)
        maximum_output_tokens = ChatModelLibraryService._positive_int(
            metadata.get("maximum_output_tokens")
            or metadata.get("max_output_tokens")
            or metadata.get("max_tokens")
        ) or (profile.maximum_output_tokens if profile is not None else None)
        context_profile_source = str(
            metadata.get("context_profile_source")
            or (profile.metadata_source if profile is not None else "unknown")
        )
        return {
            "id": item.name,
            "name": item.name,
            "description": item.description,
            "provider": item.provider,
            "capabilities": capabilities,
            "supports_tools": supports_tools,
            "supports_structured_output": supports_structured_output,
            "supports_vision": supports_vision,
            "supports_embeddings": supports_embeddings,
            "tool_support_source": tool_support_source,
            "protocol": (
                str(metadata["protocol"])
                if isinstance(metadata.get("protocol"), str)
                else None
            ),
            "agent_selection_disabled_reason": (
                str(metadata["agent_selection_disabled_reason"])
                if isinstance(metadata.get("agent_selection_disabled_reason"), str)
                else None
            ),
            "context_window_tokens": context_window_tokens,
            "maximum_output_tokens": maximum_output_tokens,
            "context_profile_source": context_profile_source,
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    @staticmethod
    def _capability_state(
        metadata: dict[str, object],
        capabilities: list[str],
        metadata_key: str,
        capability_names: tuple[str, ...],
    ) -> bool | None:
        explicit = metadata.get(metadata_key)
        if isinstance(explicit, bool):
            return explicit
        normalized = {str(value).strip().lower() for value in capabilities}
        if any(name in normalized for name in capability_names):
            return True
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _positive_int(value: object) -> int | None:
        if value is None or not isinstance(value, (str, int, float)):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    # -------------------------------------------------------------------------
    def list_models(
        self,
        *,
        ollama_url: str,
        cloud_provider: str | None = None,
        include_probe_status: bool = True,
    ) -> dict[str, object]:
        normalized_ollama_url = self.normalize_ollama_url(ollama_url)
        cloud: list[dict[str, object]] = [
            self.model_payload(item) for item in get_cloud_model_catalog()
        ]
        sources: dict[str, dict[str, object]] = {}
        if cloud_provider in DYNAMIC_CLOUD_PROVIDERS:
            dynamic_descriptors, source = self._refresh_dynamic_catalog(cloud_provider)
            cloud.extend(self.model_payload(item) for item in dynamic_descriptors)
            sources[cloud_provider] = {
                **source,
                **(
                    self._structured_probe_status(cloud_provider)
                    if include_probe_status
                    else {}
                ),
            }
        deduped_cloud: dict[tuple[str, str], dict[str, object]] = {}
        for entry in cloud:
            key = (str(entry.get("provider", "")), str(entry.get("id", "")))
            deduped_cloud[key] = entry
        local, ollama_status = self._list_ollama_models(
            normalized_ollama_url,
            include_probe_status=include_probe_status,
        )
        sources["ollama"] = ollama_status
        return {
            "cloud": list(deduped_cloud.values()),
            "local": local,
            "sources": sources,
        }

    # -------------------------------------------------------------------------
    def find_cached_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
    ) -> dict[str, object] | None:
        """Find model metadata without performing any provider I/O.

        Context assembly calls this method exclusively.  Dynamic catalogs are
        populated by explicit model-list/readiness requests and are therefore
        never refreshed recursively while building a chat request.
        """

        normalized_provider = provider.strip()
        normalized_model = model_name.strip()
        if not normalized_provider or not normalized_model:
            return None
        now = monotonic()
        dynamic_cached = self._dynamic_catalog_cache.get(normalized_provider)
        ollama_cached = self._ollama_model_cache.get(
            self.normalize_ollama_url(ollama_url)
        )
        candidates = [*get_cloud_model_catalog()]
        if dynamic_cached is not None and dynamic_cached.expires_at > now:
            candidates.extend(dynamic_cached.models)
        if ollama_cached is not None and ollama_cached.expires_at > now:
            candidates.extend(ollama_cached.models)
        for item in candidates:
            if item.provider != normalized_provider or item.name != normalized_model:
                continue
            # Context assembly is deliberately cache-only.  In particular,
            # do not call Ollama /api/show here: that enrichment is an
            # explicit model-readiness operation and would reintroduce
            # provider I/O into the request context boundary.
            return self.model_payload(item)
        return None

    # -------------------------------------------------------------------------
    def _refresh_dynamic_catalog(
        self, provider_name: str
    ) -> tuple[list[ModelDescriptor], dict[str, object]]:
        now = monotonic()
        cached = self._dynamic_catalog_cache.get(provider_name)
        if cached is not None and cached.expires_at > now:
            return list(cached.models), dict(cached.source)
        # Catalog refresh is an explicit operation.  Serialize refreshes so
        # concurrent settings/model requests do not fan out to the provider.
        with self._catalog_lock:
            now = monotonic()
            cached = self._dynamic_catalog_cache.get(provider_name)
            if cached is not None and cached.expires_at > now:
                return list(cached.models), dict(cached.source)
            try:
                provider = self.provider_factory.get_provider(provider_name)
                models = list(provider.list_models())
                source: dict[str, object] = {
                    "ok": True,
                    "reachable": True,
                    "message": None,
                    "model_count": len(models),
                    "stale": False,
                }
                self._dynamic_catalog_cache[provider_name] = _CachedModelDescriptors(
                    expires_at=now + self.dynamic_catalog_ttl_s,
                    models=models,
                    source=source,
                )
                return models, source
            except Exception as exc:
                message = str(exc) or f"Could not load {provider_name} models."
                if cached is not None and cached.models:
                    source: dict[str, object] = {
                        **cached.source,
                        "ok": False,
                        "reachable": False,
                        "message": message,
                        "stale": True,
                    }
                    self._dynamic_catalog_cache[provider_name] = _CachedModelDescriptors(
                        expires_at=now + self.dynamic_catalog_failure_ttl_s,
                        models=list(cached.models),
                        source=source,
                    )
                    return list(cached.models), source
                source: dict[str, object] = {
                    "ok": False,
                    "reachable": False,
                    "message": message,
                    "model_count": 0,
                    "stale": False,
                }
                self._dynamic_catalog_cache[provider_name] = _CachedModelDescriptors(
                    expires_at=now + self.dynamic_catalog_failure_ttl_s,
                    models=[],
                    source=source,
                )
                return [], source

    # -------------------------------------------------------------------------
    def find_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
        require_provider_availability: bool = False,
        include_probe_status: bool = True,
    ) -> dict[str, object] | None:
        dynamic_cloud_provider = (
            provider if provider in DYNAMIC_CLOUD_PROVIDERS else None
        )
        library = self.list_models(
            ollama_url=self.normalize_ollama_url(ollama_url),
            cloud_provider=dynamic_cloud_provider,
            include_probe_status=include_probe_status,
        )
        if require_provider_availability and provider in DYNAMIC_CLOUD_PROVIDERS:
            sources_value = library.get("sources", {})
            sources = (
                cast(dict[str, object], sources_value)
                if is_json_object(sources_value)
                else {}
            )
            source = sources.get(provider)
            if is_json_object(source) and not bool(source.get("ok")):
                raise ModelLibrarySourceError(
                    str(source.get("message") or f"Could not load {provider} models.")
                )
        for bucket in ("cloud", "local"):
            for item in json_array(library.get(bucket, [])):
                item_object = json_object(item)
                if (
                    item_object.get("provider") == provider
                    and item_object.get("name") == model_name
                ):
                    if provider == "ollama":
                        self._enrich_ollama_context_metadata(
                            item_object,
                            model_name=model_name,
                            ollama_url=ollama_url,
                        )
                    return item_object
        return None

    # -------------------------------------------------------------------------
    def _enrich_ollama_context_metadata(
        self,
        item: dict[str, object],
        *,
        model_name: str,
        ollama_url: str,
    ) -> None:
        """Attach provider-declared local context metadata to one model.

        The normal local model listing remains lightweight.  A selected model
        gets one additional ``/api/show`` lookup so settings and request
        budgeting can share the same exact provider metadata without deriving
        a limit from a model name or family.
        """

        ollama = OllamaProvider(
            base_url=self.normalize_ollama_url(ollama_url),
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        get_metadata = getattr(ollama, "get_model_context_metadata", None)
        if not callable(get_metadata):
            return
        try:
            metadata = get_metadata(model_name)
        except Exception:
            return
        if not is_json_object(metadata):
            return
        item_metadata = item.get("metadata")
        merged = dict(item_metadata) if is_json_object(item_metadata) else {}
        merged.update(metadata)
        item["metadata"] = merged
        for key in (
            "context_window_tokens",
            "maximum_output_tokens",
            "context_profile_source",
        ):
            if metadata.get(key) is not None:
                item[key] = metadata[key]

    # -------------------------------------------------------------------------
    @staticmethod
    def normalize_ollama_url(ollama_url: str) -> str:
        normalized = (ollama_url or "").strip() or OLLAMA_DEFAULT_HOST
        if normalized.startswith("http://localhost"):
            return "http://127.0.0.1" + normalized[len("http://localhost") :]
        if normalized.startswith("https://localhost"):
            return "https://127.0.0.1" + normalized[len("https://localhost") :]
        return normalized

    # -------------------------------------------------------------------------
    def _list_ollama_models(
        self,
        ollama_url: str,
        *,
        include_probe_status: bool = True,
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        cached_models = self._ollama_model_cache.get(ollama_url)
        now = monotonic()
        if cached_models is not None and cached_models.expires_at > now:
            return (
                [self.model_payload(model) for model in cached_models.models],
                {
                    **cached_models.source,
                    **(
                        self._structured_probe_status("ollama")
                        if include_probe_status
                        else {}
                    ),
                },
            )
        cached = self._ollama_unavailable_cache.get(ollama_url)
        if cached is not None and cached.expires_at > now:
            return [], {
                "ok": False,
                "reachable": False,
                "message": cached.message,
                "model_count": 0,
                **(
                    self._structured_probe_status("ollama")
                    if include_probe_status
                    else {}
                ),
            }
        self._ollama_unavailable_cache.pop(ollama_url, None)
        ollama = OllamaProvider(
            base_url=ollama_url,
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        local_models = ollama.list_models()
        if not local_models and ollama.last_list_models_error:
            message = ollama.last_list_models_error
            self._ollama_unavailable_cache[ollama_url] = _CachedOllamaFailure(
                expires_at=now + self.ollama_unavailable_ttl_s,
                message=message,
            )
            return [], {
                "ok": False,
                "reachable": False,
                "message": message,
                "model_count": 0,
                **(
                    self._structured_probe_status("ollama")
                    if include_probe_status
                    else {}
                ),
            }
        self._ollama_model_cache[ollama_url] = _CachedModelDescriptors(
            expires_at=now + self.dynamic_catalog_ttl_s,
            models=list(local_models),
            source={
                "ok": True,
                "reachable": True,
                "message": None,
                "model_count": len(local_models),
                "stale": False,
            },
        )
        return (
            [self.model_payload(model) for model in local_models],
            {
                "ok": True,
                "reachable": True,
                "message": None,
                "model_count": len(local_models),
                **(
                    self._structured_probe_status("ollama")
                    if include_probe_status
                    else {}
                ),
            },
        )
