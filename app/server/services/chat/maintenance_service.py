from __future__ import annotations

from collections.abc import Callable

from server.domain.chat import (
    ModelCardDescriptor,
    OllamaHealthResponse,
    OllamaPullRequest,
    OllamaPullResponse,
    OllamaRefreshResponse,
    VectorizationResponse,
)
from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.ollama import OllamaProvider
from server.services.vector.indexer import VectorIndexer


class ChatMaintenanceService:
    def __init__(
        self,
        *,
        get_ollama_url: Callable[[], str],
        vector_indexer: VectorIndexer,
        model_library_service: ChatModelLibraryService | None = None,
        ollama_tool_capability_cache: OllamaToolCapabilityCache | None = None,
    ) -> None:
        self.get_ollama_url = get_ollama_url
        self.vector_indexer = vector_indexer
        self.model_library_service = model_library_service or ChatModelLibraryService(
            ollama_tool_capability_cache=ollama_tool_capability_cache
        )
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )

    def refresh_ollama_models(self) -> OllamaRefreshResponse:
        provider = OllamaProvider(
            base_url=self.get_ollama_url(),
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        library_models = provider.list_library_models()
        local_models = provider.list_models()
        return OllamaRefreshResponse(
            status="ok",
            library_models=[model.name for model in library_models],
            local_models=[model.name for model in local_models],
            local_model_capabilities=[
                ModelCardDescriptor.model_validate(
                    self.model_library_service.model_payload(model)
                )
                for model in local_models
            ],
        )

    def pull_ollama_model(self, request: OllamaPullRequest) -> OllamaPullResponse:
        model_name = request.model.strip()
        if not model_name:
            raise ValueError("model is required")
        provider = OllamaProvider(
            base_url=self.get_ollama_url(),
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        return OllamaPullResponse.model_validate(provider.pull_model(model=model_name))

    def get_ollama_health(self) -> OllamaHealthResponse:
        provider = OllamaProvider(
            base_url=self.get_ollama_url(),
            tool_capability_cache=self.ollama_tool_capability_cache,
        )
        return OllamaHealthResponse.model_validate(provider.health_check())

    def sync_vectors(self) -> VectorizationResponse:
        return VectorizationResponse.model_validate(self.vector_indexer.sync())

    def rebuild_vectors(self) -> VectorizationResponse:
        return VectorizationResponse.model_validate(self.vector_indexer.rebuild())
