from __future__ import annotations

from dataclasses import dataclass

from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.capability_resolver import CapabilityResolver
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.direct_turn_response import DirectTurnResponseService
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.native_tool_loop import NativeToolLoop
from server.services.agent.orchestrator import AgentOrchestrator
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.pipeline_router import DeterministicAgentRouter
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_argument_builder import ToolArgumentBuilder
from server.services.agent.tool_planner import DeterministicToolPlanner
from server.services.chat.maintenance_service import ChatMaintenanceService
from server.services.chat.model_library import ChatModelLibraryService
from server.services.chat.settings_service import ChatSettingsService
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.chat.history_service import ChatHistoryService
from server.services.geospatial.composition import GeospatialRuntime
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder


###############################################################################
@dataclass(frozen=True)
class ChatRuntime:
    settings_service: ChatSettingsService
    model_library_service: ChatModelLibraryService
    maintenance_service: ChatMaintenanceService
    agent_orchestrator: AgentOrchestrator
    conversation_repository: ConversationRepository
    history_service: ChatHistoryService
    task_state_service: ConversationTaskStateService


###############################################################################
def build_chat_runtime(
    search_orchestrator: LocationSearchOrchestrator,
    database: SQLiteRepository,
    *,
    geospatial_runtime: GeospatialRuntime,
) -> ChatRuntime:
    settings_repo = ModelSettingsRepository(database)
    credentials_repo = geospatial_runtime.credentials_repo
    crypto_service = geospatial_runtime.crypto_service
    history_repository = ChatHistoryRepository(database)
    conversation_repository = ConversationRepository(database)
    ollama_tool_capability_cache = OllamaToolCapabilityCache()
    llm_factory = LLMFactory(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
        ollama_tool_capability_cache=ollama_tool_capability_cache,
    )
    model_library_service = ChatModelLibraryService(
        ollama_tool_capability_cache=ollama_tool_capability_cache,
        provider_factory=llm_factory,
    )
    settings_service = ChatSettingsService(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
        model_library_service=model_library_service,
    )

    capability_registry = geospatial_runtime.capability_registry
    runtime_registry = geospatial_runtime.runtime_registry
    geospatial_api_service = geospatial_runtime.api_service
    parser_service = ParserService(
        llm_factory=llm_factory,
        settings_repo=settings_repo,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    location_memory_service = LocationMemoryService()
    location_resolver = LocationResolver()
    policy_engine = PolicyEngine(
        location_resolver=location_resolver,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    request_builder = RequestBuilder(capability_registry=capability_registry)
    agent_tool_catalog_service = AgentToolCatalogService(
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
        search_orchestrator=search_orchestrator,
        request_builder=request_builder,
        location_resolver=location_resolver,
        tool_registry=tool_registry,
        policy_engine=policy_engine,
        geospatial_api_service=geospatial_api_service,
    )
    native_tool_loop = NativeToolLoop(
        provider_factory=llm_factory,
        tool_registry=tool_registry,
    )
    history_service = ChatHistoryService(history_repository)
    response_synthesizer = GroundedResponseSynthesizer(
        settings_repo=settings_repo,
        llm_factory=llm_factory,
    )
    task_state_service = ConversationTaskStateService()
    pipeline_router = DeterministicAgentRouter()
    tool_planner = DeterministicToolPlanner(
        ToolArgumentBuilder(capability_registry=capability_registry)
    )
    tool_plan_executor = ToolPlanExecutor(tool_registry=tool_registry)
    direct_turn_response_service = DirectTurnResponseService(
        task_state_service=task_state_service,
        history_service=history_service,
        response_synthesizer=response_synthesizer,
    )

    return ChatRuntime(
        settings_service=settings_service,
        model_library_service=model_library_service,
        maintenance_service=ChatMaintenanceService(
            get_ollama_url=settings_service.get_ollama_url,
            model_library_service=model_library_service,
            ollama_tool_capability_cache=ollama_tool_capability_cache,
        ),
        history_service=history_service,
        task_state_service=task_state_service,
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
            history_service=history_service,
            conversation_repository=conversation_repository,
            response_synthesizer=response_synthesizer,
            task_state_service=task_state_service,
            pipeline_router=pipeline_router,
            tool_planner=tool_planner,
            tool_plan_executor=tool_plan_executor,
            direct_turn_response_service=direct_turn_response_service,
            capability_resolver=CapabilityResolver(
                capability_registry=capability_registry,
                runtime_registry=runtime_registry,
            ),
        ),
        conversation_repository=conversation_repository,
    )
