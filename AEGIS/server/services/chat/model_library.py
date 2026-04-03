from __future__ import annotations

from AEGIS.server.services.llm.cloud_catalog import get_cloud_model_catalog
from AEGIS.server.services.llm.ollama import OllamaProvider


class ChatModelLibraryService:
    def list_models(self, *, ollama_url: str) -> dict[str, list[dict[str, object]]]:
        cloud = [
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
        return {"cloud": cloud, "local": local}
