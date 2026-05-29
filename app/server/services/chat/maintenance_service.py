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


OllamaProviderFactory = Callable[[str, OllamaToolCapabilityCache], OllamaProvider]


def create_ollama_provider(
    base_url: str,
    tool_capability_cache: OllamaToolCapabilityCache,
) -> OllamaProvider:
    return OllamaProvider(
        base_url=base_url,
        tool_capability_cache=tool_capability_cache,
    )

###############################################################################
class ChatMaintenanceService:
    def __init__(
        self,
        *,
        get_ollama_url: Callable[[], str],
        vector_indexer: VectorIndexer,
        model_library_service: ChatModelLibraryService | None = None,
        ollama_tool_capability_cache: OllamaToolCapabilityCache | None = None,
        ollama_provider_factory: OllamaProviderFactory = create_ollama_provider,
    ) -> None:
        self.get_ollama_url = get_ollama_url
        self.vector_indexer = vector_indexer
        self.model_library_service = model_library_service or ChatModelLibraryService(
            ollama_tool_capability_cache=ollama_tool_capability_cache
        )
        self.ollama_tool_capability_cache = (
            ollama_tool_capability_cache or OllamaToolCapabilityCache()
        )
        self.ollama_provider_factory = ollama_provider_factory

    # -------------------------------------------------------------------------
    def refresh_ollama_models(self) -> OllamaRefreshResponse:
        provider = self._ollama_provider()
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

    # -------------------------------------------------------------------------
    def pull_ollama_model(self, request: OllamaPullRequest) -> OllamaPullResponse:
        model_name = request.model.strip()
        if not model_name:
            raise ValueError("model is required")
        provider = self._ollama_provider()
        return OllamaPullResponse.model_validate(provider.pull_model(model=model_name))

    # -------------------------------------------------------------------------
    def get_ollama_health(self) -> OllamaHealthResponse:
        provider = self._ollama_provider()
        return OllamaHealthResponse.model_validate(provider.health_check())

    # -------------------------------------------------------------------------
    def sync_vectors(self) -> VectorizationResponse:
        return VectorizationResponse.model_validate(self.vector_indexer.sync())

    # -------------------------------------------------------------------------
    def rebuild_vectors(self) -> VectorizationResponse:
        return VectorizationResponse.model_validate(self.vector_indexer.rebuild())

    # -------------------------------------------------------------------------
    def _ollama_provider(self) -> OllamaProvider:
        return self.ollama_provider_factory(
            self.get_ollama_url(),
            self.ollama_tool_capability_cache,
        )
