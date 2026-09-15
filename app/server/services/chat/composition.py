from __future__ import annotations

from dataclasses import dataclass

from server.configurations.settings import AgentExecutionSettings
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.agent_evidence import AgentEvidenceRepository
from server.repositories.database.sqlite import SQLiteRepository
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.native_v2_turn import AgentTurnRunner
from server.services.agent.capability_router import CapabilityRouter
from server.services.agent.native_v2_tools import register_agent_tools
from server.services.agent.location_resolver import LocationResolver
from server.services.agent.native_orchestrator import NativeAgentOrchestrator
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.tool_executor import ToolExecutor
from server.services.chat.maintenance_service import (
    ChatMaintenanceService,
    create_ollama_provider,
)
from server.services.chat.model_library import ChatModelLibraryService
from server.services.chat.settings_service import ChatSettingsService
from server.services.chat.structured_probe import StructuredProbeService
from server.services.chat.history_service import ChatHistoryService
from server.services.geospatial.composition import GeospatialRuntime
from server.services.llm.factory import LLMFactory
from server.services.llm.ollama_capability_cache import OllamaToolCapabilityCache
from server.services.llm.context_profile_resolver import ModelContextProfileResolver
from server.services.llm.transport import LLMTransportPolicy

###############################################################################
@dataclass(frozen=True)
class ChatRuntime:
    settings_service: ChatSettingsService
    model_library_service: ChatModelLibraryService
    maintenance_service: ChatMaintenanceService
    agent_orchestrator: NativeAgentOrchestrator
    conversation_repository: ConversationRepository
    history_service: ChatHistoryService
    structured_probe_service: StructuredProbeService | None = None
    agent_loop: AgentLoop | None = None
    agent_turn_runner: AgentTurnRunner | None = None

###############################################################################
def build_chat_runtime(
    database: SQLiteRepository,
    *,
    geospatial_runtime: GeospatialRuntime,
    application_timezone: str = "UTC",
    execution_settings: AgentExecutionSettings | None = None,
) -> ChatRuntime:
    settings_repo = ModelSettingsRepository(database)
    credentials_repo = geospatial_runtime.credentials_repo
    crypto_service = geospatial_runtime.crypto_service
    history_repository = ChatHistoryRepository(database)
    conversation_repository = ConversationRepository(database)
    evidence_repository = AgentEvidenceRepository(database)
    ollama_tool_capability_cache = OllamaToolCapabilityCache()
    llm_transport_policy = LLMTransportPolicy.from_execution_settings(
        execution_settings
    )
    llm_factory = LLMFactory(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
        ollama_tool_capability_cache=ollama_tool_capability_cache,
        transport_policy=llm_transport_policy,
    )
    model_library_service = ChatModelLibraryService(
        ollama_tool_capability_cache=ollama_tool_capability_cache,
        provider_factory=llm_factory,
        transport_policy=llm_transport_policy,
    )
    context_profile_resolver = ModelContextProfileResolver(
        model_library_service=model_library_service,
        settings_repo=settings_repo,
    )
    settings_service = ChatSettingsService(
        settings_repo=settings_repo,
        credentials_repo=credentials_repo,
        crypto_service=crypto_service,
        model_library_service=model_library_service,
        context_profile_resolver=context_profile_resolver,
    )

    capability_registry = geospatial_runtime.capability_registry
    runtime_registry = geospatial_runtime.runtime_registry
    geospatial_api_service = geospatial_runtime.api_service
    structured_probe_service = StructuredProbeService(
        provider_factory=llm_factory,
        settings_service=settings_service,
    )
    settings_service.structured_probe_service = structured_probe_service
    model_library_service.set_structured_probe_service(structured_probe_service)
    location_resolver = LocationResolver()
    policy_engine = PolicyEngine(
        location_resolver=location_resolver,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
    )
    tool_registry = ToolRegistry(runtime_registry=runtime_registry)
    register_agent_tools(
        tool_registry,
        capability_registry=capability_registry,
        runtime_registry=runtime_registry,
        provider_registry=geospatial_runtime.provider_registry,
        evidence_repository=evidence_repository,
        location_resolver=location_resolver,
        geospatial_api_service=geospatial_api_service,
    )
    agent_loop = AgentLoop(
        provider_factory=llm_factory,
        capability_router=CapabilityRouter(
            capability_registry=capability_registry,
            runtime_registry=runtime_registry,
        ),
        tool_registry=tool_registry,
        tool_executor=ToolExecutor(
            tool_registry=tool_registry,
            policy_engine=policy_engine,
            timeout_seconds=(
                execution_settings.tool_execution_seconds
                if execution_settings is not None
                else 45.0
            ),
        ),
        transport_policy=llm_transport_policy,
    )
    agent_turn_runner = AgentTurnRunner(
        agent_loop=agent_loop,
        execution_settings=execution_settings,
    )
    history_service = ChatHistoryService(history_repository)
    agent_orchestrator = NativeAgentOrchestrator(
        agent_turn_runner=agent_turn_runner,
        settings_repo=settings_repo,
        history_service=history_service,
        conversation_repository=conversation_repository,
        evidence_repository=evidence_repository,
        context_profile_resolver=context_profile_resolver,
        execution_settings=execution_settings,
        application_timezone=application_timezone,
        agent_loop=agent_loop,
    )

    return ChatRuntime(
        settings_service=settings_service,
        model_library_service=model_library_service,
        maintenance_service=ChatMaintenanceService(
            get_ollama_url=settings_service.get_ollama_url,
            model_library_service=model_library_service,
            ollama_tool_capability_cache=ollama_tool_capability_cache,
            ollama_provider_factory=lambda base_url, cache: create_ollama_provider(
                base_url,
                cache,
                transport_policy=llm_transport_policy,
            ),
        ),
        history_service=history_service,
        agent_loop=agent_loop,
        agent_turn_runner=agent_turn_runner,
        agent_orchestrator=agent_orchestrator,
        conversation_repository=conversation_repository,
        structured_probe_service=structured_probe_service,
    )
