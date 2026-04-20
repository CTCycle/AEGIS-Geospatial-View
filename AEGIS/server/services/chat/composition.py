from __future__ import annotations

from dataclasses import dataclass

from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.chat.maintenance_service import ChatMaintenanceService
from AEGIS.server.services.chat.model_library import ChatModelLibraryService
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.vector.indexer import VectorIndexer


@dataclass(frozen=True)
class ChatRuntime:
    settings_service: ChatSettingsService
    model_library_service: ChatModelLibraryService
    vector_indexer: VectorIndexer
    maintenance_service: ChatMaintenanceService
    agent_orchestrator: AgentOrchestrator


def build_chat_runtime(search_orchestrator: LocationSearchOrchestrator) -> ChatRuntime:
    settings_repo = ModelSettingsRepository()
    settings_service = ChatSettingsService(settings_repo=settings_repo)
    vector_indexer = VectorIndexer()
    return ChatRuntime(
        settings_service=settings_service,
        model_library_service=ChatModelLibraryService(),
        vector_indexer=vector_indexer,
        maintenance_service=ChatMaintenanceService(
            get_ollama_url=settings_service.get_ollama_url,
            vector_indexer=vector_indexer,
        ),
        agent_orchestrator=AgentOrchestrator(search_orchestrator=search_orchestrator),
    )
