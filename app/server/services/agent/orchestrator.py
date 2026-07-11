from __future__ import annotations

from typing import Any
from uuid import uuid4

from server.common.logger import logger as LOGGER
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    TaskFailureDetail,
    VisualizationUpdate,
)
from server.domain.chat import ChatOperationResult, ChatTurnRequest, ChatTurnResponse
from server.repositories.model_settings import ModelSettingsRepository
from server.repositories.conversation_context import ConversationContextRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.capability_resolver import CapabilityResolver
from server.services.agent.conversation_state import (
    ConversationTaskStateService,
)
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.agent.context_assembler import AgentContextAssembler
from server.domain.agent.context import ConversationDirective
from server.services.agent.native_tool_loop import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    NativeToolLoop,
)
from server.services.agent.overlay_inference import OverlayInferenceService
from server.services.agent.pipeline_router import DeterministicAgentRouter
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_history import AgentTurnHistoryService
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler
from server.services.agent.turn_support import AgentTurnSupport
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_planner import DeterministicToolPlanner
from server.services.chat.history_service import ChatHistoryService
from server.services.llm.factory import LLMFactory
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

###############################################################################
class AgentOrchestrator:
    _compose_map_session_message = staticmethod(AgentResponseBuilder.compose_map_session_message)
    _compose_direct_tool_message = staticmethod(AgentResponseBuilder.compose_direct_tool_message)
    _compose_general_question_message = staticmethod(AgentTurnSupport.compose_general_question_message)
    _has_parser_runtime_failure = staticmethod(AgentTurnSupport.has_parser_runtime_failure)

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        search_orchestrator: LocationSearchOrchestrator,
        parser_service: ParserService,
        location_memory_service: LocationMemoryService,
        policy_engine: PolicyEngine,
        tool_registry: ToolRegistry,
        request_builder: RequestBuilder,
        native_tool_loop: NativeToolLoop | None = None,
        agent_tool_catalog_service: AgentToolCatalogService | None = None,
        overlay_inference_service: OverlayInferenceService | None = None,
        settings_repo: ModelSettingsRepository | None = None,
        history_service: ChatHistoryService | None = None,
        history_repo: ChatHistoryService | None = None,
        conversation_context_repository: ConversationContextRepository | None = None,
        task_state_service: ConversationTaskStateService | None = None,
        pipeline_router: DeterministicAgentRouter | None = None,
        tool_planner: DeterministicToolPlanner | None = None,
        tool_plan_executor: ToolPlanExecutor | None = None,
        capability_resolver: CapabilityResolver | None = None,
        response_synthesizer: GroundedResponseSynthesizer | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.parser_service = parser_service
        self.location_memory_service = location_memory_service
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.request_builder = request_builder
        self.settings_repo = settings_repo or ModelSettingsRepository()
        self.agent_tool_catalog_service = (
            agent_tool_catalog_service
            or AgentToolCatalogService(
                search_orchestrator=self.search_orchestrator,
                request_builder=self.request_builder,
                location_resolver=self.policy_engine.location_resolver,
                tool_registry=self.tool_registry,
                policy_engine=self.policy_engine,
            )
        )
        self.agent_tool_catalog_service.register_with(self.tool_registry)
        self.overlay_inference_service = overlay_inference_service or OverlayInferenceService()
        self.native_tool_loop = native_tool_loop or NativeToolLoop(
            provider_factory=LLMFactory(settings_repo=self.settings_repo),
            tool_registry=self.tool_registry,
        )
        self.history_service = history_service or history_repo or ChatHistoryService()
        self.conversation_context_repository = conversation_context_repository
        self.task_state_service = task_state_service or ConversationTaskStateService()
        self.instruction_state_service = ConversationInstructionService()
        self._active_directives: dict[str, list[ConversationDirective]] = {}
        self.context_assembler = AgentContextAssembler()
        self._context_packages: dict[str, Any] = {}
        self._persisted_context_state: dict[str, dict[str, Any]] = {}
        self.pipeline_router = pipeline_router or DeterministicAgentRouter()
        self.tool_planner = tool_planner or DeterministicToolPlanner()
        self.tool_plan_executor = tool_plan_executor or ToolPlanExecutor(
            tool_registry=self.tool_registry
        )
        self.capability_resolver = capability_resolver or CapabilityResolver()
        self.response_synthesizer = response_synthesizer or GroundedResponseSynthesizer(
            settings_repo=self.settings_repo
        )
        self.turn_history_service = AgentTurnHistoryService(
            history_service=self.history_service, location_memory_service=self.location_memory_service
        )
        self.turn_state_assembler = AgentTurnStateAssembler(
            search_orchestrator=self.search_orchestrator,
            policy_engine=self.policy_engine,
            request_builder=self.request_builder,
            overlay_inference_service=self.overlay_inference_service,
            location_memory_service=self.location_memory_service,
            response_synthesizer=self.response_synthesizer,
            history_service=self.history_service,
            task_state_service=self.task_state_service,
        )

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback=None,
    ) -> ChatTurnResponse:
        conversation_id = payload.conversation_id
        repository = self.conversation_context_repository
        persisted: dict[str, Any] | None = None
        directives: list[ConversationDirective] = []
        if conversation_id is not None:
            if repository is None:
                repository = ConversationContextRepository()
                self.conversation_context_repository = repository
            if hasattr(repository, "read_state"):
                persisted = repository.read_state(conversation_id)
                self._persisted_context_state[conversation_id] = persisted
                self.task_state_service.hydrate(
                    conversation_id, persisted.get("task_snapshot")
                )
                directives = [
                    ConversationDirective.model_validate(item)
                    for item in persisted.get("active_instructions", [])
                ]
                directives = self.instruction_state_service.apply_user_message(
                    directives,
                    payload.message,
                    len(
                        self.history_service.list_recent_messages(
                            repository.resolve_chat_session_id(conversation_id),
                            limit=10_000,
                        )
                    )
                    + 1,
                )
                self._active_directives[conversation_id] = directives
        response = await self._run_turn(payload, progress_callback)
        response = self._with_phase_usage(response)
        if conversation_id is not None and repository is not None and persisted is not None:
            revision = repository.write_state(
                conversation_id,
                expected_revision=int(persisted["context_revision"]),
                active_instructions=[item.model_dump(mode="json") for item in directives],
                task_snapshot=self.task_state_service.serialize(conversation_id),
                memory_snapshot=response.memory_snapshot,
                conversation_summary=(
                    self._context_packages[conversation_id].conversation_summary
                    if conversation_id in self._context_packages
                    else None
                ),
                summary_through_turn_index=(
                    self._context_packages[conversation_id].summarized_through_turn_index
                    if conversation_id in self._context_packages
                    else None
                ),
            )
            response = response.model_copy(update={"context_revision": revision})
        return response

    # -------------------------------------------------------------------------
    def _with_phase_usage(self, response: ChatTurnResponse) -> ChatTurnResponse:
        phases: dict[str, dict[str, Any]] = {}
        if response.context_usage is not None:
            phases["parser"] = response.context_usage.model_dump(mode="json", exclude={"phases"})
        loop_usages = getattr(self.native_tool_loop, "last_context_usages", [])
        if loop_usages:
            phases["native_loop"] = {
                "iterations": loop_usages,
                "estimated_input_tokens": sum(int(item.get("estimated_input_tokens") or 0) for item in loop_usages),
            }
        synthesis = getattr(self.response_synthesizer, "last_context_usage", None)
        if isinstance(synthesis, dict):
            phases["synthesis"] = synthesis
        if response.context_usage is None or not phases:
            return response
        inputs = [
            int(item.get("estimated_input_tokens") or 0)
            for item in phases.values()
            if isinstance(item, dict)
        ]
        usage = response.context_usage.model_copy(
            update={
                "phases": phases,
                "peak_request_tokens": max(inputs, default=0),
                "total_input_tokens": sum(inputs),
                "total_output_tokens": 0,
            }
        )
        return response.model_copy(update={"context_usage": usage})

    # -------------------------------------------------------------------------
    async def _run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback=None,
    ) -> ChatTurnResponse:
        request_id = payload.request_id or f"chat-{uuid4().hex[:12]}"
        LOGGER.info(
            "chat_turn_start request_id=%s session_id=%s message_length=%s",
            request_id,
            payload.session_id,
            len(payload.message),
        )
        if payload.conversation_id is not None:
            context_repository = self.conversation_context_repository
            if context_repository is None:
                context_repository = ConversationContextRepository()
                self.conversation_context_repository = context_repository
            canonical_session_id = context_repository.resolve_chat_session_id(payload.conversation_id)
            if payload.session_id is not None:
                context_repository.validate_session(
                    payload.conversation_id, payload.session_id
                )
            session = self.history_service.upsert_session(
                canonical_session_id, title=payload.title
            )
        else:
            session = self.history_service.upsert_session(
                payload.session_id, title=payload.title
            )
        existing_response = self.turn_history_service.load_existing_response(session.id, request_id)
        if existing_response is not None:
            return existing_response
        if self.turn_history_service.find_history_message_by_request_id(
            session_id=session.id,
            role="user",
            request_id=request_id,
        ) is None:
            self.history_service.append_message(
                session_id=session.id,
                role="user",
                content=payload.message,
                request_id=request_id,
            )

        recent_messages = self.history_service.list_recent_messages(session.id, limit=200)
        for index in range(len(recent_messages) - 1, -1, -1):
            message = recent_messages[index]
            if message.get("role") == "user" and message.get("content") == payload.message:
                recent_messages.pop(index)
                break
        latest_contract = self.history_service.get_latest_turn_contract(session.id)
        latest_memory = self.history_service.get_latest_memory_snapshot(session.id)
        conversation_key = payload.conversation_id or f"session:{session.id}"
        state_before = self.task_state_service.snapshot(conversation_key)
        latest_memory = self.turn_history_service.merge_conversation_state_memory(
            latest_memory,
            state_before.active_visualization,
        )

        settings = self.settings_repo.get_or_create()
        context_package = self.context_assembler.assemble(
            provider=settings.agent_model_provider,
            model=settings.agent_model_name,
            current_user_message=payload.message,
            messages=recent_messages,
            directives=self.instruction_state_service.active(
                self._active_directives.get(conversation_key, [])
            ),
            task_state=state_before.model_dump(mode="json"),
            map_memory=latest_memory,
            prior_summary=(
                self._persisted_context_state.get(conversation_key, {}).get(
                    "conversation_summary"
                )
            ),
        )
        self._context_packages[conversation_key] = context_package
        recent_messages = context_package.recent_messages

        parser_kwargs = {
            "user_message": payload.message,
            "memory_snapshot": latest_memory,
            "conversation_messages": recent_messages,
        }
        if isinstance(self.parser_service, ParserService):
            parser_kwargs["active_instructions"] = [
                item.model_dump(mode="json")
                for item in self.instruction_state_service.active(
                    self._active_directives.get(conversation_key, [])
                )
            ]
            parser_kwargs["task_snapshot"] = state_before.model_dump(mode="json")
        turn_contract = self.parser_service.parse_turn(**parser_kwargs)
        turn_contract = self.turn_history_service.merge_memory_location_signals(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        turn_contract = self.capability_resolver.resolve(turn_contract)
        LOGGER.info(
            "chat_turn_parsed request_id=%s conversation_key=%s task=%s action=%s relationship=%s specialist_candidate=%s viewport_scope=%s basemap=%s layers=%s",
            request_id,
            conversation_key,
            turn_contract.task_class,
            turn_contract.normalized_action.action_id,
            turn_contract.relationship,
            self.pipeline_router.select_specialist(turn_contract),
            turn_contract.viewport_intent.scope if turn_contract.viewport_intent is not None else None,
            turn_contract.requested_basemap,
            ",".join(turn_contract.requested_layers) if turn_contract.requested_layers else "-",
        )
        if progress_callback is not None:
            progress_callback(
                "parsed",
                {
                    "request_id": request_id,
                    "session_id": session.id,
                    "task_class": turn_contract.task_class,
                    "action_id": turn_contract.normalized_action.action_id,
                    "requires_location": turn_contract.normalized_action.requires_location,
                    "location_signal_count": len(turn_contract.location_signals),
                    "ambiguities": list(turn_contract.ambiguities),
                },
            )
        specialist = self.pipeline_router.select_specialist(turn_contract)
        task = self.task_state_service.start_task(
            conversation_key,
            turn_contract,
            specialist,
        )
        LOGGER.info(
            "chat_turn_routed request_id=%s conversation_key=%s specialist=%s active_visualization=%s",
            request_id,
            conversation_key,
            specialist,
            bool(latest_memory.get("active_visualization")) if isinstance(latest_memory, dict) else False,
        )
        context_usage = self.parser_service.last_context_usage
        if AgentTurnSupport.has_parser_authentication_failure(turn_contract):
            assistant_message = (
                "I could not use the configured agent model because the saved API key was rejected. "
                "Open Model Settings and replace the key before using that cloud model."
            )
            decision = AgentTurnSupport.build_direct_reject_decision(turn_contract.normalized_action.action_id)
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
            failure = TaskFailureDetail(
                stage="structured_intent_extraction",
                component="agent_model",
                sanitized_error="The configured agent credential was rejected.",
                recovery_suggestion="Replace the saved agent API key in Model Settings.",
                user_explanation=assistant_message,
            )
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="failed",
                failure=failure,
                progress_summary="Intent extraction failed.",
            )
            self.history_service.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                request_id=request_id,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            LOGGER.info(
                "chat_turn_parser_authentication_failed request_id=%s session_id=%s",
                request_id,
                session.id,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
                failure_diagnostic=failure,
            )
        if AgentTurnSupport.has_parser_runtime_failure(turn_contract):
            assistant_message = (
                "I could not process this request because the configured agent model could not perform structured extraction. "
                "Open Model Settings, choose an agent model that supports structured output and tool calling, or refresh/pull the configured Ollama model."
            )
            decision = AgentTurnSupport.build_direct_reject_decision(turn_contract.normalized_action.action_id)
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
            failure = TaskFailureDetail(
                stage="structured_intent_extraction",
                component="agent_model",
                sanitized_error="The configured agent model could not perform structured extraction.",
                recovery_suggestion="Open Model Settings, choose an agent model that supports structured output and tool calling, or refresh/pull the configured Ollama model.",
                user_explanation=assistant_message,
            )
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="failed",
                failure=failure,
                progress_summary="Intent extraction failed.",
            )
            self.history_service.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                request_id=request_id,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            LOGGER.info(
                "chat_turn_parser_unavailable request_id=%s session_id=%s",
                request_id,
                session.id,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
                failure_diagnostic=failure,
            )

        if turn_contract.relationship == "failure_inquiry":
            failure = self.task_state_service.latest_failure(conversation_key)
            if failure is None:
                assistant_message = (
                    "The exact cause was not captured for the previous request. "
                    "That is an instrumentation gap; no structured failed task is available in this conversation."
                )
            else:
                assistant_message = failure.user_explanation
                if failure.recovery_suggestion:
                    assistant_message = (
                        f"{assistant_message} Recovery: {failure.recovery_suggestion}"
                    )
            operation = ChatOperationResult(
                kind="failure_diagnostic",
                status="success" if failure is not None else "partial",
                message=assistant_message,
            )
            decision = AgentTurnSupport.build_direct_reject_decision(turn_contract.normalized_action.action_id)
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="completed",
                progress_summary="Explained the latest captured failure.",
            )
            self.history_service.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                request_id=request_id,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "request_id": request_id,
                },
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
                failure_diagnostic=failure,
            )

        if turn_contract.clarification_plan is not None:
            return await self.turn_state_assembler.build_partial_clarification_response(
                request_id=request_id,
                session_id=session.id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                context_usage=context_usage,
            )

        if turn_contract.task_class == "general_question" or AgentTurnSupport.is_capability_question(turn_contract.user_text):
            fallback_message = AgentTurnSupport.compose_general_question_message(
                turn_contract.user_text,
                recent_messages,
            )
            operation = ChatOperationResult(
                kind="capability_catalog" if AgentTurnSupport.is_capability_question(turn_contract.user_text) else "direct_answer",
                status="success",
                message=fallback_message,
            )
            assistant_message = self.response_synthesizer.synthesize(
                user_text=turn_contract.user_text,
                fallback_text=fallback_message,
                operation=operation,
                task_status="completed",
            )
            operation = operation.model_copy(update={"message": assistant_message})
            self.history_service.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                request_id=request_id,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": None,
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="completed",
                progress_summary="Answered without geospatial tools.",
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=AgentTurnSupport.build_direct_reject_decision(turn_contract.normalized_action.action_id),
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
            )

        preflight_decision = self.policy_engine.evaluate_preflight(turn_contract)
        if preflight_decision is not None:
            assistant_message = (
                preflight_decision.clarification.question
                if preflight_decision.clarification is not None
                else "I cannot execute this request with the current policy constraints."
            )
            operation = AgentResponseBuilder.build_preflight_operation_result(
                decision_state=preflight_decision.plan.state,
                assistant_message=assistant_message,
            )
            if preflight_decision.plan.state == "clarify":
                assistant_message = self.response_synthesizer.synthesize(
                    user_text=turn_contract.user_text,
                    fallback_text=assistant_message,
                    operation=operation,
                    clarification_plan={
                        "question": assistant_message,
                        "reason": (
                            preflight_decision.clarification.reason
                            if preflight_decision.clarification is not None
                            else "Additional information is required."
                        ),
                        "blocking_fields": (
                            preflight_decision.clarification.missing_fields
                            if preflight_decision.clarification is not None
                            else []
                        ),
                    },
                    task_status="needs_clarification",
                )
                operation = operation.model_copy(update={"message": assistant_message})
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="needs_clarification"
                if preflight_decision.plan.state == "clarify"
                else "failed",
                blocking_ambiguity=assistant_message
                if preflight_decision.plan.state == "clarify"
                else None,
                progress_summary=assistant_message,
            )
            self.history_service.append_message(
                session_id=session.id,
                role="assistant",
                content=assistant_message,
                request_id=request_id,
                structured_payload={
                    "turn_contract": turn_contract.model_dump(mode="json"),
                    "decision": preflight_decision.model_dump(mode="json"),
                    "operation": operation.model_dump(mode="json"),
                    "memory_snapshot": latest_memory,
                    "previous_turn_contract": latest_contract,
                    "request_id": request_id,
                },
                tool_payload=None,
                map_session=None,
            )
            return ChatTurnResponse(
                request_id=request_id,
                session_id=session.id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=preflight_decision,
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
            )

        settings = self.settings_repo.get_or_create()
        tool_plan = self.tool_planner.build_plan(
            turn_contract,
            specialist,
            latest_memory,
        )
        LOGGER.info(
            "chat_turn_plan request_id=%s specialist=%s tools=%s steps=%d visualization_update=%s",
            request_id,
            specialist,
            ",".join(tool_plan.selected_tools) if tool_plan.selected_tools else "-",
            len(tool_plan.steps),
            tool_plan.visualization_update,
        )
        if progress_callback is not None:
            progress_callback(
                "policy",
                {
                    "request_id": request_id,
                    "session_id": session.id,
                    "specialist": specialist,
                    "planned_tools": list(tool_plan.selected_tools),
                },
            )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="routed",
            progress_summary=f"Routed to {specialist}.",
            tool_plan=tool_plan,
        )
        constraints = self.policy_engine.build_agent_constraints(
            turn_contract,
            latest_memory,
        )
        native_context = AgentExecutionContext(
            request_id=request_id,
            session_id=str(session.id),
            parsed_request=turn_contract.model_dump(mode="json"),
            map_state=latest_memory if isinstance(latest_memory, dict) else {},
            policy_constraints={
                "requires_location": constraints.requires_location,
                "blocked_patterns": constraints.blocked_patterns,
                "allowed_tool_names": constraints.allowed_tool_names,
                "allowed_capability_ids": [
                    step.capability_id
                    for step in tool_plan.steps
                    if step.capability_id is not None
                ],
                **constraints.metadata,
            },
            metadata={
                "previous_turn_contract": latest_contract,
                "allowed_native_tools": tool_plan.selected_tools,
                "allowed_capability_ids": [
                    step.capability_id
                    for step in tool_plan.steps
                    if step.capability_id is not None
                ],
                "specialist": specialist,
            },
        )
        deterministic_tools_available = (
            isinstance(self.agent_tool_catalog_service, AgentToolCatalogService)
            and (bool(tool_plan.steps) or bool(tool_plan.visualization_update))
            and all(
                self.tool_registry.has_native_tool(step.tool_name)
                for step in tool_plan.steps
            )
        )
        if deterministic_tools_available:
            return await self._execute_planned_turn(
                request_id=request_id,
                session_id=session.id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                latest_contract=latest_contract,
                context_usage=context_usage,
                native_context=native_context,
                tool_plan=tool_plan,
                progress_callback=progress_callback,
            )
        tool_builder = getattr(
            self.agent_tool_catalog_service,
            "build_native_tools",
            None,
        )
        native_tools = (
            tool_builder(native_context)
            if callable(tool_builder)
            else self.tool_registry.list_native_tools()
        )
        if not native_tools:
            native_tools = self.tool_registry.list_native_tools()
        tool_loop_result = await self.native_tool_loop.run(
            AgentToolLoopRequest(
                provider=settings.agent_model_provider,
                model=settings.agent_model_name,
                messages=AgentTurnSupport.build_native_agent_messages(
                    turn_contract=turn_contract,
                    memory_snapshot=latest_memory,
                    constraints=constraints,
                    active_instructions=[
                        item.model_dump(mode="json")
                        for item in self.instruction_state_service.active(
                            self._active_directives.get(conversation_key, [])
                        )
                    ],
                    task_snapshot=self.task_state_service.serialize(conversation_key),
                ),
                tools=native_tools,
                temperature=0.2,
                max_tokens=None,
                context=native_context,
            )
        )
        decision_trace_steps = [
            "1.parse_structured_request",
            "2.build_policy_constraints",
            "3.native_tool_loop",
            f"4.stop:{tool_loop_result.stopped_reason}",
        ]
        assistant_message = tool_loop_result.final_text or "Done."
        tool_payload = {
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in tool_loop_result.tool_calls
            ],
            "tool_results": [
                {
                    "tool_call_id": result.tool_call_id,
                    "name": result.name,
                    "content": result.content,
                    "is_error": result.is_error,
                    "error": result.error,
                }
                for result in tool_loop_result.tool_results
            ],
            "iterations": tool_loop_result.iterations,
            "stopped_reason": tool_loop_result.stopped_reason,
        }
        map_session = await self.turn_state_assembler.build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None:
            map_session = tool_loop_result.map_session
        direct_result = self.turn_state_assembler.extract_direct_result_from_tool_results(tool_payload)
        capability_selection = self.turn_state_assembler.extract_capability_selection_from_tool_results(tool_payload)
        if map_session is None and capability_selection is not None:
            map_session = await self.turn_state_assembler.build_map_session_from_capability_selection(
                capability_selection=capability_selection,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
            )
        if map_session is None and AgentResponseBuilder.should_build_fallback_map(
            task_class=turn_contract.task_class,
            requires_location=turn_contract.normalized_action.requires_location,
            location_signals=turn_contract.location_signals,
            tool_payload=tool_payload,
        ):
            map_session = await self.turn_state_assembler.build_map_session_from_turn_contract(turn_contract, latest_memory)
        memory_snapshot = await self.turn_state_assembler.build_updated_memory_snapshot(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        assistant_message = AgentResponseBuilder.build_verified_assistant_message(
            tool_loop_result.final_text,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        operation = AgentResponseBuilder.build_verified_operation_result(
            assistant_message=assistant_message,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
            user_text=turn_contract.user_text,
            is_capability_question=AgentTurnSupport.is_capability_question(
                turn_contract.user_text
            ),
        )
        assistant_message = self.response_synthesizer.synthesize(
            user_text=turn_contract.user_text,
            fallback_text=assistant_message,
            operation=operation,
            map_session=map_session,
            direct_result=direct_result,
            task_status="completed" if operation.status == "success" else "partial",
            active_instructions=[
                item.model_dump(mode="json")
                for item in self.instruction_state_service.active(
                    self._active_directives.get(conversation_key, [])
                )
            ],
            task_snapshot=self.task_state_service.serialize(conversation_key),
        )
        operation = operation.model_copy(update={"message": assistant_message})
        decision = AgentResponseBuilder.build_final_decision(
            action_id=turn_contract.normalized_action.action_id,
            operation=operation,
            trace_steps=decision_trace_steps,
        )
        failure = self.turn_state_assembler.failure_from_operation(operation, tool_payload)
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="failed" if failure is not None else "completed",
            progress_summary=operation.message,
            failure=failure,
            tool_plan=tool_plan,
            tool_result_refs=[
                str(item.get("tool_call_id"))
                for item in tool_payload.get("tool_results") or []
                if isinstance(item, dict) and item.get("tool_call_id")
            ],
        )
        self.task_state_service.set_active_visualization(conversation_key, map_session)

        self.history_service.append_message(
            session_id=session.id,
            role="assistant",
            content=assistant_message,
            request_id=request_id,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
                "memory_snapshot": memory_snapshot,
                "previous_turn_contract": latest_contract,
                "request_id": request_id,
            },
            tool_payload=tool_payload,
            map_session=map_session.model_dump(mode="json") if map_session is not None else None,
        )

        LOGGER.info(
            "chat_turn_complete request_id=%s session_id=%s state=%s",
            request_id,
            session.id,
            decision.plan.state,
        )
        return ChatTurnResponse(
            request_id=request_id,
            session_id=session.id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            tool_payload=tool_payload,
            map_session=map_session,
            memory_snapshot=memory_snapshot,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            tool_plan=tool_plan,
            failure_diagnostic=failure,
        )

    # -------------------------------------------------------------------------
    async def _execute_planned_turn(
        self,
        *,
        request_id: str,
        session_id: int,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract,
        latest_memory: dict[str, Any],
        latest_contract: dict[str, Any] | None,
        context_usage,
        native_context: AgentExecutionContext,
        tool_plan,
        progress_callback=None,
    ) -> ChatTurnResponse:
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="in_progress",
            progress_summary="Executing validated tool plan.",
            tool_plan=tool_plan,
        )
        planned_results = await self.tool_plan_executor.execute(
            tool_plan,
            native_context,
            on_tool_started=(
                lambda step: progress_callback(
                    "tool_call_started",
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "tool_call_id": step.step_id,
                        "name": step.tool_name,
                    },
                )
                if progress_callback is not None
                else None
            ),
            on_tool_completed=(
                lambda result: progress_callback(
                    "tool_call_completed",
                    {
                        "request_id": request_id,
                        "session_id": session_id,
                        "tool_call_id": result.step_id,
                        "name": result.provenance.tool_name,
                        "ok": result.ok,
                        "error": result.error_message,
                    },
                )
                if progress_callback is not None
                else None
            ),
        )
        tool_payload = {
            "tool_plan": tool_plan.model_dump(mode="json"),
            "tool_calls": [
                {
                    "id": result.step_id,
                    "name": result.provenance.tool_name,
                    "arguments": next(
                        step.arguments
                        for step in tool_plan.steps
                        if step.step_id == result.step_id
                    ),
                }
                for result in planned_results
            ],
            "tool_results": [
                {
                    "tool_call_id": result.step_id,
                    "name": result.provenance.tool_name,
                    "content": {
                        "ok": result.ok,
                        "data": result.data,
                        "error": (
                            {
                                "code": result.error_code,
                                "message": result.error_message,
                            }
                            if not result.ok
                            else None
                        ),
                    },
                    "is_error": not result.ok,
                    "error": result.error_message,
                    "provenance": result.provenance.model_dump(mode="json"),
                }
                for result in planned_results
            ],
            "iterations": 1,
            "stopped_reason": "planned_execution",
        }
        required_failures = [
            result
            for result in planned_results
            if not result.ok
            and next(
                step.required for step in tool_plan.steps if step.step_id == result.step_id
            )
        ]
        map_session = await self.turn_state_assembler.build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None and tool_plan.visualization_update:
            map_session = await self.turn_state_assembler.build_map_session_from_turn_contract(
                turn_contract,
                latest_memory,
            )
        direct_result = self.turn_state_assembler.extract_direct_result_from_tool_results(tool_payload)
        if required_failures and map_session is None and direct_result is None:
            first = required_failures[0]
            assistant_message = first.error_message or "The required geospatial tool failed."
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
        elif (
            turn_contract.task_class == "map_search"
            and map_session is None
            and direct_result is None
        ):
            assistant_message = (
                "I could not create a map session from this request. "
                "Try a more specific place name or choose an available map layer."
            )
            operation = ChatOperationResult(
                kind="error",
                status="failed",
                message=assistant_message,
            )
        else:
            assistant_message = AgentResponseBuilder.build_verified_assistant_message(
                "",
                map_session=map_session,
                direct_result=direct_result,
                tool_payload=tool_payload,
            )
            operation = AgentResponseBuilder.build_verified_operation_result(
                assistant_message=assistant_message,
                map_session=map_session,
                direct_result=direct_result,
                tool_payload=tool_payload,
                user_text=turn_contract.user_text,
                is_capability_question=False,
            )
            if any(not result.ok for result in planned_results) and operation.status == "success":
                operation = operation.model_copy(update={"status": "partial"})
            assistant_message = self.response_synthesizer.synthesize(
                user_text=turn_contract.user_text,
                fallback_text=assistant_message,
                operation=operation,
                map_session=map_session,
                direct_result=direct_result,
                task_status=(
                    "completed" if operation.status == "success" else "partial"
                ),
                active_instructions=[
                    item.model_dump(mode="json")
                    for item in self.instruction_state_service.active(
                        self._active_directives.get(conversation_key, [])
                    )
                ],
                task_snapshot=self.task_state_service.serialize(conversation_key),
            )
            operation = operation.model_copy(update={"message": assistant_message})
        decision = AgentResponseBuilder.build_final_decision(
            action_id=turn_contract.normalized_action.action_id,
            operation=operation,
            trace_steps=[
                "1.parse_structured_request",
                "2.update_conversation_task",
                "3.route_specialist",
                "4.build_tool_plan",
                "5.execute_dependency_levels",
                "6.validate_tool_results",
                "7.build_frontend_payload",
            ],
        )
        memory_snapshot = await self.turn_state_assembler.build_updated_memory_snapshot(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        failure = self.turn_state_assembler.failure_from_operation(operation, tool_payload)
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="failed" if failure is not None else "completed",
            progress_summary=operation.message,
            failure=failure,
            tool_plan=tool_plan,
            tool_result_refs=[result.step_id for result in planned_results],
        )
        self.task_state_service.set_active_visualization(conversation_key, map_session)
        visualization_update = VisualizationUpdate(
            basemap_replacement=tool_plan.visualization_update.get("basemap_replacement")
            if isinstance(tool_plan.visualization_update.get("basemap_replacement"), str)
            else turn_contract.requested_basemap,
            add_layer_ids=list(turn_contract.requested_layers),
        )
        if progress_callback is not None and map_session is not None:
            progress_callback(
                "map_session_created",
                {
                    "request_id": request_id,
                    "session_id": session_id,
                    "map_session": map_session.model_dump(mode="json"),
                },
            )
        self.history_service.append_message(
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            request_id=request_id,
            structured_payload={
                "turn_contract": turn_contract.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
                "operation": operation.model_dump(mode="json"),
                "memory_snapshot": memory_snapshot,
                "previous_turn_contract": latest_contract,
                "request_id": request_id,
            },
            tool_payload=tool_payload,
            map_session=map_session.model_dump(mode="json") if map_session else None,
        )
        return ChatTurnResponse(
            request_id=request_id,
            session_id=session_id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            tool_payload=tool_payload,
            map_session=map_session,
            memory_snapshot=memory_snapshot,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            tool_plan=tool_plan,
            failure_diagnostic=failure,
            visualization_update=visualization_update,
        )


