from __future__ import annotations

from dataclasses import dataclass
from time import monotonic
from typing import Literal

from server.common.constants import OLLAMA_DEFAULT_HOST
from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama import OllamaProvider
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.types import ModelDescriptor

###############################################################################
@dataclass
class _CachedOllamaFailure:
    expires_at: float
    message: str

###############################################################################
class ModelLibrarySourceError(RuntimeError):
    pass

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
        supports_tools = "tools" in capabilities
        supports_structured_output = (
            "structured" in capabilities or "structured_output" in capabilities
        )
        supports_vision = "vision" in capabilities
        supports_embeddings = "embeddings" in capabilities
        tool_support_source = str(
            metadata.get(
                "tool_support_source",
                "catalog"
                if item.provider in {"openai", "google"}
                else "provider"
                if item.provider == "deepseek"
                else "unknown",
            )
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
            "metadata": metadata,
        }

    # -------------------------------------------------------------------------
    def list_models(
        self,
        *,
        ollama_url: str,
        cloud_provider: Literal["deepseek"] | None = None,
    ) -> dict[str, object]:
        normalized_ollama_url = self.normalize_ollama_url(ollama_url)
        cloud: list[dict[str, object]] = [
            self.model_payload(item) for item in get_cloud_model_catalog()
        ]
        sources: dict[str, dict[str, object]] = {}
        if cloud_provider == "deepseek":
            try:
                provider = self.provider_factory.get_provider("deepseek")
                deepseek_models = [
                    self.model_payload(item) for item in provider.list_models()
                ]
                cloud.extend(deepseek_models)
                sources["deepseek"] = {
                    "ok": True,
                    "message": None,
                    "model_count": len(deepseek_models),
                }
            except Exception as exc:
                sources["deepseek"] = {
                    "ok": False,
                    "message": str(exc) or "Could not load DeepSeek models.",
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
        dynamic_cloud_provider: Literal["deepseek"] | None = (
            "deepseek" if provider == "deepseek" else None
        )
        library = self.list_models(
            ollama_url=self.normalize_ollama_url(ollama_url),
            cloud_provider=dynamic_cloud_provider,
        )
        if require_provider_availability and provider == "deepseek":
            sources = library.get("sources", {})
            source = (
                sources.get("deepseek")
                if isinstance(sources, dict)
                else None
            )
            if isinstance(source, dict) and not bool(source.get("ok")):
                raise ModelLibrarySourceError(
                    str(source.get("message") or "Could not load DeepSeek models.")
                )
        for bucket in ("cloud", "local"):
            for item in library.get(bucket, []):
                if item.get("provider") == provider and item.get("name") == model_name:
                    return item
        return None

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
