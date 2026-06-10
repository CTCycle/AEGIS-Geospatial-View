from __future__ import annotations

from dataclasses import dataclass

from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.native_tool_loop import NativeToolLoop
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.chat.maintenance_service import ChatMaintenanceService
from server.services.chat.model_library import ChatModelLibraryService
from server.services.chat.settings_service import ChatSettingsService
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder


@dataclass(frozen=True)
class ChatRuntime:
    settings_service: ChatSettingsService
    model_library_service: ChatModelLibraryService
    maintenance_service: ChatMaintenanceService
    agent_orchestrator: AgentOrchestrator


def build_chat_runtime(search_orchestrator: LocationSearchOrchestrator) -> ChatRuntime:
    settings_repo = ModelSettingsRepository()
    ollama_tool_capability_cache = OllamaToolCapabilityCache()
    model_library_service = ChatModelLibraryService(
        ollama_tool_capability_cache=ollama_tool_capability_cache
    )
    settings_service = ChatSettingsService(
        settings_repo=settings_repo,
        model_library_service=model_library_service,
    )

    runtime_registry = RuntimeRegistry()
    parser_service = ParserService(settings_repo=settings_repo)
    location_memory_service = LocationMemoryService()
    location_resolver = LocationResolver()
    policy_engine = PolicyEngine(
        location_resolver=location_resolver,
        capability_registry=search_orchestrator.capability_registry,
        runtime_registry=runtime_registry,
    )
    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    agent_tool_catalog_service = AgentToolCatalogService(
        capability_registry=search_orchestrator.capability_registry,
        runtime_registry=runtime_registry,
        policy_engine=policy_engine,
    )
    native_tool_loop = NativeToolLoop(
        provider_factory=LLMFactory(
            settings_repo=settings_repo,
            ollama_tool_capability_cache=ollama_tool_capability_cache,
        ),
        tool_registry=tool_registry,
    )
    request_builder = RequestBuilder()

    return ChatRuntime(
        settings_service=settings_service,
        model_library_service=model_library_service,
        maintenance_service=ChatMaintenanceService(
            get_ollama_url=settings_service.get_ollama_url,
            model_library_service=model_library_service,
            ollama_tool_capability_cache=ollama_tool_capability_cache,
        ),
        agent_orchestrator=AgentOrchestrator(
            search_orchestrator=search_orchestrator,
            parser_service=parser_service,
            location_memory_service=location_memory_service,
            policy_engine=policy_engine,
            tool_registry=tool_registry,
            request_builder=request_builder,
            native_tool_loop=native_tool_loop,
            agent_tool_catalog_service=agent_tool_catalog_service,
            settings_repo=settings_repo,
        ),
    )
