from __future__ import annotations

from server.services.llm.cloud_catalog import get_cloud_model_catalog
from server.services.llm.ollama import OllamaProvider


class ChatModelLibraryService:
    def list_models(self, *, ollama_url: str) -> dict[str, list[dict[str, object]]]:
        cloud: list[dict[str, object]] = [
            {
                "id": item.name,
                "name": item.name,
                "description": item.description,
                "provider": item.provider,
                "capabilities": item.capabilities,
                "metadata": item.metadata,
            }
            for item in get_cloud_model_catalog()
        ]
        ollama = OllamaProvider(base_url=ollama_url)
        for item in ollama.list_library_models():
            cloud.append(
                {
                    "id": item.name,
                    "name": item.name,
                    "description": item.description,
                    "provider": item.provider,
                    "capabilities": item.capabilities,
                    "metadata": item.metadata,
                }
            )
        deduped_cloud: dict[tuple[str, str], dict[str, object]] = {}
        for entry in cloud:
            key = (str(entry.get("provider", "")), str(entry.get("id", "")))
            deduped_cloud[key] = entry
        local = [
            {
                "id": model.name,
                "name": model.name,
                "description": model.description,
                "provider": model.provider,
                "capabilities": model.capabilities,
                "metadata": model.metadata,
            }
            for model in ollama.list_models()
        ]
        return {"cloud": list(deduped_cloud.values()), "local": local}
