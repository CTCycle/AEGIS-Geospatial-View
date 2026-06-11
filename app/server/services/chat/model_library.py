from __future__ import annotations

from typing import Literal

from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama import OllamaProvider
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.types import ModelDescriptor


###############################################################################
class ChatModelLibraryService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        ollama_tool_capability_cache: OllamaToolCapabilityCache | None = None,
        provider_factory: LLMFactory | None = None,
    ) -> None:
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )
        self.provider_factory = provider_factory or LLMFactory(
            ollama_tool_capability_cache=self.ollama_tool_capability_cache
        )

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
    ) -> dict[str, list[dict[str, object]]]:
        cloud: list[dict[str, object]] = [
            self.model_payload(item) for item in get_cloud_model_catalog()
        ]
        if cloud_provider == "deepseek":
            provider = self.provider_factory.get_provider("deepseek")
            cloud.extend(
                self.model_payload(item) for item in provider.list_models()
            )
        ollama = OllamaProvider(
            base_url=ollama_url,
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        for item in ollama.list_library_models():
            cloud.append(self.model_payload(item))
        deduped_cloud: dict[tuple[str, str], dict[str, object]] = {}
        for entry in cloud:
            key = (str(entry.get("provider", "")), str(entry.get("id", "")))
            deduped_cloud[key] = entry
        local = [self.model_payload(model) for model in ollama.list_models()]
        return {"cloud": list(deduped_cloud.values()), "local": local}

    # -------------------------------------------------------------------------
    def find_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
    ) -> dict[str, object] | None:
        dynamic_cloud_provider: Literal["deepseek"] | None = (
            "deepseek" if provider == "deepseek" else None
        )
        library = self.list_models(
            ollama_url=ollama_url,
            cloud_provider=dynamic_cloud_provider,
        )
        for bucket in ("cloud", "local"):
            for item in library.get(bucket, []):
                if item.get("provider") == provider and item.get("name") == model_name:
                    return item
        return None
