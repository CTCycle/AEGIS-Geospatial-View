from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from dataclasses import dataclass
from time import monotonic
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
    ) -> None:
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )
        self.provider_factory = provider_factory
        self.ollama_unavailable_ttl_s = ollama_unavailable_ttl_s
        self._ollama_unavailable_cache: dict[str, _CachedOllamaFailure] = {}

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
        except TypeError, ValueError:
            return None
        return parsed if parsed > 0 else None

    # -------------------------------------------------------------------------
    def list_models(
        self,
        *,
        ollama_url: str,
        cloud_provider: str | None = None,
    ) -> dict[str, object]:
        normalized_ollama_url = self.normalize_ollama_url(ollama_url)
        cloud: list[dict[str, object]] = [
            self.model_payload(item) for item in get_cloud_model_catalog()
        ]
        sources: dict[str, dict[str, object]] = {}
        if cloud_provider in DYNAMIC_CLOUD_PROVIDERS:
            try:
                provider = self.provider_factory.get_provider(cloud_provider)
                dynamic_models = [
                    self.model_payload(item) for item in provider.list_models()
                ]
                cloud.extend(dynamic_models)
                sources[cloud_provider] = {
                    "ok": True,
                    "message": None,
                    "model_count": len(dynamic_models),
                }
            except Exception as exc:
                sources[cloud_provider] = {
                    "ok": False,
                    "message": str(exc) or f"Could not load {cloud_provider} models.",
                    "model_count": 0,
                }
        deduped_cloud: dict[tuple[str, str], dict[str, object]] = {}
        for entry in cloud:
            key = (str(entry.get("provider", "")), str(entry.get("id", "")))
            deduped_cloud[key] = entry
        local, ollama_status = self._list_ollama_models(normalized_ollama_url)
        sources["ollama"] = ollama_status
        return {
            "cloud": list(deduped_cloud.values()),
            "local": local,
            "sources": sources,
        }

    # -------------------------------------------------------------------------
    def find_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
        require_provider_availability: bool = False,
    ) -> dict[str, object] | None:
        dynamic_cloud_provider = (
            provider if provider in DYNAMIC_CLOUD_PROVIDERS else None
        )
        library = self.list_models(
            ollama_url=self.normalize_ollama_url(ollama_url),
            cloud_provider=dynamic_cloud_provider,
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
    ) -> tuple[list[dict[str, object]], dict[str, object]]:
        cached = self._ollama_unavailable_cache.get(ollama_url)
        now = monotonic()
        if cached is not None and cached.expires_at > now:
            return [], {
                "ok": False,
                "reachable": False,
                "message": cached.message,
                "model_count": 0,
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
            }
        return (
            [self.model_payload(model) for model in local_models],
            {
                "ok": True,
                "reachable": True,
                "message": None,
                "model_count": len(local_models),
            },
        )
