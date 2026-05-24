from __future__ import annotations

from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.ollama import OllamaProvider


class ChatModelLibraryService:
    @staticmethod
    def _model_payload(item) -> dict[str, object]:  # noqa: ANN001
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
                "catalog" if item.provider in {"openai", "google"} else "unknown",
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

    def list_models(self, *, ollama_url: str) -> dict[str, list[dict[str, object]]]:
        cloud: list[dict[str, object]] = [
            self._model_payload(item) for item in get_cloud_model_catalog()
        ]
        ollama = OllamaProvider(base_url=ollama_url)
        for item in ollama.list_library_models():
            cloud.append(self._model_payload(item))
        deduped_cloud: dict[tuple[str, str], dict[str, object]] = {}
        for entry in cloud:
            key = (str(entry.get("provider", "")), str(entry.get("id", "")))
            deduped_cloud[key] = entry
        local = [self._model_payload(model) for model in ollama.list_models()]
        return {"cloud": list(deduped_cloud.values()), "local": local}

    def find_model(
        self,
        *,
        provider: str,
        model_name: str,
        ollama_url: str,
    ) -> dict[str, object] | None:
        library = self.list_models(ollama_url=ollama_url)
        for bucket in ("cloud", "local"):
            for item in library.get(bucket, []):
                if item.get("provider") == provider and item.get("name") == model_name:
                    return item
        return None
