from __future__ import annotations

from collections.abc import Callable

from server.contracts.chat import (
    ModelCardDescriptor,
    OllamaHealthResponse,
    OllamaPullRequest,
    OllamaPullResponse,
    OllamaRefreshResponse,
)
from server.services.chat.model_library import ChatModelLibraryService
from server.services.llm.ollama import OllamaProvider
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.errors import LLMProviderRequestError
from server.services.llm.transport import LLMTransportPolicy

OllamaProviderFactory = Callable[[str, OllamaToolCapabilityCache], OllamaProvider]

###############################################################################
def create_ollama_provider(
    base_url: str,
    tool_capability_cache: OllamaToolCapabilityCache,
    *,
    transport_policy: LLMTransportPolicy | None = None,
) -> OllamaProvider:
    return OllamaProvider(
        base_url=base_url,
        tool_capability_cache=tool_capability_cache,
        transport_policy=transport_policy,
    )

###############################################################################
class ChatMaintenanceService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        get_ollama_url: Callable[[], str],
        model_library_service: ChatModelLibraryService,
        ollama_tool_capability_cache: OllamaToolCapabilityCache,
        ollama_provider_factory: OllamaProviderFactory = create_ollama_provider,
    ) -> None:
        self.get_ollama_url = get_ollama_url
        self.model_library_service = model_library_service
        self.ollama_tool_capability_cache = ollama_tool_capability_cache
        self.ollama_provider_factory = ollama_provider_factory

    # -------------------------------------------------------------------------
    def refresh_ollama_models(self) -> OllamaRefreshResponse:
        provider = self._ollama_provider()
        library_models = provider.list_library_models()
        self._raise_if_provider_catalog_failed(provider, "library catalog")
        local_models = provider.list_models()
        self._raise_if_provider_catalog_failed(provider, "local catalog")
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
    def _ollama_provider(self) -> OllamaProvider:
        return self.ollama_provider_factory(
            self.get_ollama_url(),
            self.ollama_tool_capability_cache,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _raise_if_provider_catalog_failed(
        provider: OllamaProvider,
        catalog_name: str,
    ) -> None:
        error_detail = getattr(provider, "last_list_library_models_error", None)
        diagnostics = getattr(
            provider, "last_list_library_models_diagnostics", {}
        )
        if catalog_name == "local catalog":
            error_detail = getattr(provider, "last_list_models_error", None)
            diagnostics = getattr(provider, "last_list_models_diagnostics", {})
        if not error_detail:
            return
        raise LLMProviderRequestError(
            provider="ollama",
            model="*",
            stage="catalog",
            code="provider_catalog_unavailable",
            retryable=False,
            diagnostics=diagnostics if isinstance(diagnostics, dict) else {},
        ) from RuntimeError(str(error_detail))
