from __future__ import annotations

from dataclasses import dataclass

from AEGIS.server.services.agent.capability_retriever import CapabilityRetriever
from AEGIS.server.services.agent.location_memory import LocationMemoryService
from AEGIS.server.services.agent.location_resolver import LocationResolver
from AEGIS.server.services.agent.orchestrator import AgentOrchestrator
from AEGIS.server.services.agent.parser_service import ParserService
from AEGIS.server.services.agent.policy_engine import PolicyEngine
from AEGIS.server.services.agent.tool_registry import ToolRegistry
from AEGIS.server.services.chat.maintenance_service import ChatMaintenanceService
from AEGIS.server.services.chat.model_library import ChatModelLibraryService
from AEGIS.server.services.chat.settings_service import ChatSettingsService
from AEGIS.server.services.geospatial.runtime_registry import RuntimeRegistry
from AEGIS.server.repositories.model_settings import ModelSettingsRepository
from AEGIS.server.services.search.orchestrator import LocationSearchOrchestrator
from AEGIS.server.services.search.request_builder import RequestBuilder
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

    runtime_registry = RuntimeRegistry()
    parser_service = ParserService()
    location_memory_service = LocationMemoryService()
    location_resolver = LocationResolver()
    capability_retriever = CapabilityRetriever()
    policy_engine = PolicyEngine(
        location_resolver=location_resolver,
        capability_retriever=capability_retriever,
    )
    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    request_builder = RequestBuilder()

    return ChatRuntime(
        settings_service=settings_service,
        model_library_service=ChatModelLibraryService(),
        vector_indexer=vector_indexer,
        maintenance_service=ChatMaintenanceService(
            get_ollama_url=settings_service.get_ollama_url,
            vector_indexer=vector_indexer,
        ),
        agent_orchestrator=AgentOrchestrator(
            search_orchestrator=search_orchestrator,
            parser_service=parser_service,
            location_memory_service=location_memory_service,
            policy_engine=policy_engine,
            tool_registry=tool_registry,
            request_builder=request_builder,
        ),
    )
