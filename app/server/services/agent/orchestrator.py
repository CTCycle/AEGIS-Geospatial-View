from __future__ import annotations

from typing import Any
from uuid import uuid4

from server.common.logger import logger as LOGGER
from server.domain.agent.decision import DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    TaskFailureDetail,
    VisualizationUpdate,
)
from server.domain.chat import ChatOperationResult, ChatTurnRequest, ChatTurnResponse
from server.domain.extraction.models import LocationSignal
from server.domain.geographics import MapSession
from server.repositories.model_settings import ModelSettingsRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.capability_resolver import CapabilityResolver
from server.services.agent.conversation_state import (
    ConversationTaskStateService,
)
from server.services.agent.location_memory import LocationMemoryService
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
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_planner import DeterministicToolPlanner
from server.services.chat.history_service import ChatHistoryService
from server.services.llm.factory import LLMFactory
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder

###############################################################################
class AgentOrchestrator:

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
        self.task_state_service = task_state_service or ConversationTaskStateService()
        self.pipeline_router = pipeline_router or DeterministicAgentRouter()
        self.tool_planner = tool_planner or DeterministicToolPlanner()
        self.tool_plan_executor = tool_plan_executor or ToolPlanExecutor(
            tool_registry=self.tool_registry
        )
        self.capability_resolver = capability_resolver or CapabilityResolver()
        self.response_synthesizer = response_synthesizer or GroundedResponseSynthesizer(
            settings_repo=self.settings_repo
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _compose_map_session_message(map_payload: dict[str, Any]) -> str:
        return AgentResponseBuilder.compose_map_session_message(map_payload)

    # -------------------------------------------------------------------------
    @staticmethod
    def _compose_direct_tool_message(tool_id: str, direct_result: dict[str, Any]) -> str:
        return AgentResponseBuilder.compose_direct_tool_message(tool_id, direct_result)

    # -------------------------------------------------------------------------
    async def run_turn(
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
        session = self.history_service.upsert_session(payload.session_id, title=payload.title)
        existing_response = self._load_existing_response(session.id, request_id)
        if existing_response is not None:
            return existing_response
        if self._find_history_message_by_request_id(
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

        recent_messages = self.history_service.list_recent_messages(session.id, limit=12)
        latest_contract = self.history_service.get_latest_turn_contract(session.id)
        latest_memory = self.history_service.get_latest_memory_snapshot(session.id)
        conversation_key = payload.conversation_id or f"session:{session.id}"
        state_before = self.task_state_service.snapshot(conversation_key)
        latest_memory = self._merge_conversation_state_memory(
            latest_memory,
            state_before.active_visualization,
        )

        turn_contract = self.parser_service.parse_turn(
            user_message=payload.message,
            memory_snapshot=latest_memory,
            conversation_messages=recent_messages,
        )
        turn_contract = self._merge_memory_location_signals(
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
        if self._has_parser_authentication_failure(turn_contract):
            assistant_message = (
                "I could not use the configured agent model because the saved API key was rejected. "
                "Open Model Settings and replace the key before using that cloud model."
            )
            decision = self._build_direct_reject_decision(turn_contract.normalized_action.action_id)
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
        if self._has_parser_runtime_failure(turn_contract):
            assistant_message = (
                "I could not process this request because the configured agent model could not perform structured extraction. "
                "Open Model Settings, choose an agent model that supports structured output and tool calling, or refresh/pull the configured Ollama model."
            )
            decision = self._build_direct_reject_decision(turn_contract.normalized_action.action_id)
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
            decision = self._build_direct_reject_decision(
                turn_contract.normalized_action.action_id
            )
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
            return await self._build_partial_clarification_response(
                request_id=request_id,
                session_id=session.id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                context_usage=context_usage,
            )

        if turn_contract.task_class == "general_question" or self._is_capability_question(turn_contract.user_text):
            fallback_message = self._compose_general_question_message(
                turn_contract.user_text,
                recent_messages,
            )
            operation = ChatOperationResult(
                kind="capability_catalog" if self._is_capability_question(turn_contract.user_text) else "direct_answer",
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
                decision=self._build_direct_reject_decision(turn_contract.normalized_action.action_id),
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
                messages=self._build_native_agent_messages(
                    turn_contract=turn_contract,
                    memory_snapshot=latest_memory,
                    constraints=constraints,
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
        map_session = await self._build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None:
            map_session = tool_loop_result.map_session
        direct_result = self._extract_direct_result_from_tool_results(tool_payload)
        capability_selection = self._extract_capability_selection_from_tool_results(tool_payload)
        if map_session is None and capability_selection is not None:
            map_session = await self._build_map_session_from_capability_selection(
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
            map_session = await self._build_map_session_from_turn_contract(turn_contract, latest_memory)
        memory_snapshot = await self._build_updated_memory_snapshot(
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
            is_capability_question=self._is_capability_question(turn_contract.user_text),
        )
        assistant_message = self.response_synthesizer.synthesize(
            user_text=turn_contract.user_text,
            fallback_text=assistant_message,
            operation=operation,
            map_session=map_session,
            direct_result=direct_result,
            task_status="completed" if operation.status == "success" else "partial",
        )
        operation = operation.model_copy(update={"message": assistant_message})
        decision = AgentResponseBuilder.build_final_decision(
            action_id=turn_contract.normalized_action.action_id,
            operation=operation,
            trace_steps=decision_trace_steps,
        )
        failure = self._failure_from_operation(operation, tool_payload)
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
        map_session = await self._build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None and tool_plan.visualization_update:
            map_session = await self._build_map_session_from_turn_contract(
                turn_contract,
                latest_memory,
            )
        direct_result = self._extract_direct_result_from_tool_results(tool_payload)
        if required_failures and map_session is None and direct_result is None:
            first = required_failures[0]
            assistant_message = first.error_message or "The required geospatial tool failed."
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
        memory_snapshot = await self._build_updated_memory_snapshot(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        failure = self._failure_from_operation(operation, tool_payload)
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

    # -------------------------------------------------------------------------
    async def _build_partial_clarification_response(
        self,
        *,
        request_id: str,
        session_id: int,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract,
        latest_memory: dict[str, Any],
        context_usage,
    ) -> ChatTurnResponse:
        clarification = turn_contract.clarification_plan
        if not isinstance(clarification, dict):
            raise ValueError("Partial clarification requires a validated clarification plan.")
        previous_raw = self.task_state_service.snapshot(
            conversation_key
        ).active_visualization
        map_session: MapSession | None = None
        removed_layers: list[str] = []
        visualization_changes = task.visualization_changes
        requested_basemap = visualization_changes.get("basemap")
        if (
            bool(clarification.get("apply_visualization_changes"))
            and isinstance(previous_raw, dict)
        ):
            try:
                previous = MapSession.model_validate(previous_raw)
                removed_layers = [
                    layer_id
                    for layer_id in previous.overlay_ids
                    if layer_id
                    in {
                        "VIIRS_SNPP_CorrectedReflectance_TrueColor",
                        "MODIS_Terra_CorrectedReflectance_TrueColor",
                    }
                ]
                retained = [
                    layer_id
                    for layer_id in previous.overlay_ids
                    if layer_id not in removed_layers
                ]
                plan = ExecutionPlan(
                    state="map_search",
                    mode="map",
                    action_id=turn_contract.normalized_action.action_id,
                    basemap_id=(
                        str(requested_basemap)
                        if isinstance(requested_basemap, str) and requested_basemap
                        else previous.basemap_id
                    ),
                    overlay_ids=retained,
                )
                request = self.request_builder.build_location_search_request(
                    plan,
                    previous.resolved_location,
                    turn_contract=turn_contract,
                    active_visualization=previous.model_dump(mode="json"),
                )
                map_session = await self.search_orchestrator.execute(request)
            except Exception as exc:
                LOGGER.warning("Could not apply partial follow-up map update", exc_info=True)
                failure = TaskFailureDetail(
                    stage="visualization_update",
                    component="search_orchestrator",
                    sanitized_error=str(exc) or "Partial follow-up map update failed.",
                    partial_results_available=True,
                    recovery_suggestion="Retry the map refinement or keep the current map view and change only the basemap.",
                    user_explanation="I could not apply the requested map refinement to the current view.",
                )
                self.task_state_service.update_task(
                    conversation_key,
                    task.task_id,
                    status="failed",
                    failure=failure,
                    progress_summary="Partial follow-up map update failed.",
                )
        question = str(clarification.get("question") or "Can you clarify the request?")
        applied_change = (
            f"I applied the valid map change to {requested_basemap}. "
            if map_session is not None and requested_basemap
            else ""
        )
        assistant_message = f"{applied_change}{question}"
        operation = ChatOperationResult(
            kind="clarification",
            status="partial",
            message=assistant_message,
            map_session=map_session,
        )
        assistant_message = self.response_synthesizer.synthesize(
            user_text=turn_contract.user_text,
            fallback_text=assistant_message,
            operation=operation,
            map_session=map_session,
            clarification_plan=clarification,
            task_status="needs_clarification",
        )
        operation = operation.model_copy(update={"message": assistant_message})
        decision = PolicyDecision(
            plan=ExecutionPlan(
                state="clarify",
                mode="map",
                action_id=turn_contract.normalized_action.action_id,
                basemap_id=map_session.basemap_id if map_session else None,
                overlay_ids=list(map_session.overlay_ids) if map_session else [],
            ),
            trace=DecisionTrace(
                steps=[
                    "follow_up.resolve_active_visualization",
                    "clarification.apply_valid_partial_changes",
                    "clarification.request_blocking_fields",
                ]
            ),
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="needs_clarification",
            blocking_ambiguity=", ".join(
                map(str, clarification.get("blocking_fields") or [])
            )
            or str(clarification.get("reason") or "clarification_required"),
            progress_summary=assistant_message,
        )
        self.task_state_service.set_active_visualization(conversation_key, map_session)
        visualization_update = VisualizationUpdate(
            basemap_replacement=(
                str(requested_basemap)
                if isinstance(requested_basemap, str) and requested_basemap
                else None
            ),
            remove_layer_ids=removed_layers,
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
                "memory_snapshot": latest_memory,
                "request_id": request_id,
            },
            map_session=map_session.model_dump(mode="json") if map_session else None,
        )
        return ChatTurnResponse(
            request_id=request_id,
            session_id=session_id,
            assistant_message=assistant_message,
            turn_contract=turn_contract,
            decision=decision,
            operation=operation,
            map_session=map_session,
            memory_snapshot=latest_memory,
            context_usage=context_usage,
            task_snapshot=self.task_state_service.snapshot(conversation_key),
            visualization_update=visualization_update,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _merge_conversation_state_memory(
        latest_memory: dict[str, Any] | None,
        active_visualization: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(latest_memory or {})
        if not isinstance(active_visualization, dict):
            return merged
        merged["active_visualization"] = active_visualization
        location = active_visualization.get("resolved_location")
        if isinstance(location, dict):
            merged["active_location"] = location
        return merged

    # -------------------------------------------------------------------------
    @staticmethod
    def _failure_from_operation(
        operation: ChatOperationResult,
        tool_payload: dict[str, Any] | None,
    ) -> TaskFailureDetail | None:
        if operation.status != "failed" and operation.kind != "error":
            return None
        failed_result = next(
            (
                item
                for item in (tool_payload or {}).get("tool_results") or []
                if isinstance(item, dict) and item.get("is_error")
            ),
            None,
        )
        error_message = operation.message
        tool_name = None
        if isinstance(failed_result, dict):
            tool_name = str(failed_result.get("name") or "") or None
            error_message = str(failed_result.get("error") or error_message)
        return TaskFailureDetail(
            stage="tool_execution" if failed_result else "response_planning",
            component="agent_pipeline",
            tool_name=tool_name,
            sanitized_error=error_message,
            partial_results_available=operation.status == "partial",
            recovery_suggestion="Clarify the request or retry after the provider is available.",
            user_explanation=operation.message,
        )

    # -------------------------------------------------------------------------
    def _load_existing_response(
        self,
        session_id: int,
        request_id: str,
    ) -> ChatTurnResponse | None:
        existing = self._find_history_message_by_request_id(
            session_id=session_id,
            role="assistant",
            request_id=request_id,
        )
        if existing is None:
            return None
        payload = existing.get("structured_payload")
        if not isinstance(payload, dict):
            return None
        response_payload = {
            "request_id": request_id,
            "session_id": session_id,
            "assistant_message": existing.get("content") or "",
            "turn_contract": payload.get("turn_contract"),
            "decision": payload.get("decision"),
            "operation": payload.get("operation"),
            "tool_payload": existing.get("tool_payload"),
            "map_session": existing.get("map_session"),
            "memory_snapshot": payload.get("memory_snapshot") or {},
            "context_usage": payload.get("context_usage"),
        }
        return ChatTurnResponse.model_validate(response_payload)

    # -------------------------------------------------------------------------
    def _find_history_message_by_request_id(
        self,
        *,
        session_id: int,
        role: str,
        request_id: str,
    ) -> dict[str, Any] | None:
        finder = getattr(self.history_service, "find_message_by_request_id", None)
        if finder is None:
            return None
        return finder(
            session_id=session_id,
            role=role,
            request_id=request_id,
        )

    # -------------------------------------------------------------------------
    def _merge_memory_location_signals(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ):
        latest_memory = latest_memory if isinstance(latest_memory, dict) else {}
        memory_signals = self.location_memory_service.resolve_explicit_references(
            turn_contract.user_text,
            latest_memory,
        )
        if not memory_signals:
            return turn_contract
        merged_signals = self._dedupe_location_signals([
            *memory_signals,
            *list(turn_contract.location_signals),
        ])
        ambiguities = [
            item
            for item in turn_contract.ambiguities
            if item not in {"missing_location", "deictic_without_memory"}
        ]
        return turn_contract.model_copy(
            update={
                "location_signals": merged_signals,
                "ambiguities": ambiguities,
            }
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _dedupe_location_signals(signals: list[LocationSignal]) -> list[LocationSignal]:
        unique: list[LocationSignal] = []
        seen: set[tuple[str, str, float | None, float | None, str]] = set()
        for signal in signals:
            key = (
                signal.signal_type,
                signal.normalized_value or signal.raw_value,
                signal.latitude,
                signal.longitude,
                signal.source,
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(signal)
        return unique

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_native_agent_messages(
        *,
        turn_contract,
        memory_snapshot: dict,
        constraints,
    ) -> list[dict[str, Any]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are the AEGIS geospatial agent. Use native tools when geospatial "
                    "catalog discovery, capability description, or execution is needed. "
                    "Do not invent tool results. Call only the provided tools by exact name. "
                    "After tool results are returned, provide a concise user-facing answer."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Parsed request:\n"
                    f"{turn_contract.model_dump_json()}\n\n"
                    f"Map memory:\n{memory_snapshot}\n\n"
                    f"Policy constraints:\n{constraints}"
                ),
            },
        ]

    # -------------------------------------------------------------------------
    @staticmethod
    def _build_direct_reject_decision(action_id: str):
        return PolicyDecision(
            plan=ExecutionPlan(state="direct_response", action_id=action_id),
            trace=DecisionTrace(steps=["general_question.direct_response"]),
        )

    # -------------------------------------------------------------------------
    @classmethod
    def _compose_general_question_message(
        cls,
        user_text: str,
        recent_messages: list[dict[str, Any]] | None = None,
    ) -> str:
        text = user_text.lower()
        if cls._asks_about_previous_user_turn(text):
            previous = cls._previous_user_message(recent_messages or [], current_text=user_text)
            if previous:
                return f"You just asked: {previous}"
            return "I do not have a previous user request in this chat yet."
        if "capabil" in text or "model" in text:
            return (
                "I can parse geospatial requests, resolve locations, build map sessions with supported basemaps and overlays, "
                "answer coordinate and weather queries through registered tools, remember the active location for follow-ups, "
                "and reject requests that try to bypass policy or reveal secrets."
            )
        return "I can help with location-based maps, coordinates, weather, rainfall, traffic layers, and related geospatial questions."

    # -------------------------------------------------------------------------
    @staticmethod
    def _asks_about_previous_user_turn(text: str) -> bool:
        return (
            "what did i just ask" in text
            or "what was my last question" in text
            or "what did i ask you to remember" in text
            or "what did i ask you to keep in mind" in text
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _previous_user_message(
        recent_messages: list[dict[str, Any]],
        *,
        current_text: str,
    ) -> str | None:
        current = str(current_text or "").strip()
        for message in reversed(recent_messages):
            if str(message.get("role") or "") != "user":
                continue
            content = str(message.get("content") or "").strip()
            if content and content != current:
                return content
        return None

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_capability_question(user_text: str) -> bool:
        text = user_text.lower()
        return "capabil" in text and any(marker in text for marker in ("model", "you", "app", "aegis"))

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_parser_runtime_failure(turn_contract) -> bool:
        if "parser_unavailable" not in set(turn_contract.ambiguities or []):
            return False
        if not hasattr(turn_contract, "task_class"):
            return True
        return (
            turn_contract.task_class == "unclear"
            or turn_contract.normalized_action.action_id == "unknown"
            or (
                turn_contract.normalized_action.requires_location
                and not turn_contract.location_signals
                and not turn_contract.conversation_context.memory_snapshot.get(
                    "active_location"
                )
            )
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _has_parser_authentication_failure(turn_contract) -> bool:
        return "parser_authentication_failed" in set(turn_contract.ambiguities or [])

    # -------------------------------------------------------------------------
    def _extract_direct_result_from_tool_results(
        self,
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(tool_payload, dict):
            return None
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            direct_result = data.get("direct_result")
            if isinstance(direct_result, dict):
                return direct_result
        return None

    # -------------------------------------------------------------------------
    def _extract_capability_selection_from_tool_results(
        self,
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if not isinstance(tool_payload, dict):
            return None
        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict):
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            selection = data.get("capability_selection")
            if isinstance(selection, dict):
                return selection
        return None

    # -------------------------------------------------------------------------
    async def _build_map_session_from_capability_selection(
        self,
        *,
        capability_selection: dict[str, Any],
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not hasattr(resolved_location, "model_dump"):
            return None
        inferred_overlay_ids = self._infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=list(capability_selection.get("overlay_ids") or []),
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=capability_selection.get("basemap_id"),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                latest_memory.get("active_visualization")
                if isinstance(latest_memory, dict)
                else None
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    async def _build_map_session_from_turn_contract(
        self,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if not hasattr(resolved_location, "model_dump"):
            return None
        inferred_overlay_ids = self._infer_overlay_ids(
            turn_contract=turn_contract,
            resolved_location=resolved_location,
            existing_overlay_ids=[],
        )
        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=self._infer_basemap_id(turn_contract),
            overlay_ids=inferred_overlay_ids,
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                latest_memory.get("active_visualization")
                if isinstance(latest_memory, dict)
                else None
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    async def _build_updated_memory_snapshot(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any] | None,
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base_snapshot = latest_memory if isinstance(latest_memory, dict) else {}
        resolved_location = await self._resolve_verified_location_for_memory(
            turn_contract=turn_contract,
            latest_memory=base_snapshot,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
        )
        if resolved_location is None:
            return base_snapshot
        return self.location_memory_service.update_memory_snapshot(
            base_snapshot,
            resolved_location,
            turn_contract.normalized_action,
        )

    # -------------------------------------------------------------------------
    async def _resolve_verified_location_for_memory(
        self,
        *,
        turn_contract,
        latest_memory: dict[str, Any],
        map_session: MapSession | None,
        direct_result: dict[str, Any] | None,
        tool_payload: dict[str, Any] | None,
    ):
        if map_session is not None:
            return map_session.resolved_location
        if direct_result is None:
            return None
        if AgentResponseBuilder.tool_payload_has_error(tool_payload):
            return None
        resolved = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory,
        )
        if hasattr(resolved, "missing_fields"):
            return None
        return resolved

    # -------------------------------------------------------------------------
    async def _build_combined_map_session_from_tool_results(
        self,
        *,
        tool_payload: dict[str, Any] | None,
        turn_contract,
        latest_memory: dict[str, Any] | None,
    ) -> MapSession | None:
        if not isinstance(tool_payload, dict):
            return None
        successful_entries: list[dict[str, Any]] = []
        overlay_ids: list[str] = []
        basemap_id: str | None = None

        for result in tool_payload.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if not isinstance(content, dict) or content.get("ok") is False:
                continue
            data = content.get("data")
            if not isinstance(data, dict):
                continue
            entry: dict[str, Any] = {"data": data}
            map_payload = data.get("map_session")
            if isinstance(map_payload, dict):
                entry["map_session"] = map_payload
                candidate_basemap = map_payload.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in map_payload.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)
            selection = data.get("capability_selection")
            if isinstance(selection, dict):
                entry["capability_selection"] = selection
                candidate_basemap = selection.get("basemap_id")
                if isinstance(candidate_basemap, str) and candidate_basemap.strip() and basemap_id is None:
                    basemap_id = candidate_basemap
                for overlay_id in selection.get("overlay_ids") or []:
                    if isinstance(overlay_id, str) and overlay_id not in overlay_ids:
                        overlay_ids.append(overlay_id)
            if entry.keys() != {"data"}:
                successful_entries.append(entry)

        if not overlay_ids and basemap_id is None:
            return None

        resolved_location = await self.policy_engine.location_resolver.resolve_location_signals(
            turn_contract.location_signals,
            latest_memory or {},
        )
        if hasattr(resolved_location, "missing_fields"):
            return None

        plan = ExecutionPlan(
            state="map_search",
            mode="map",
            action_id=turn_contract.normalized_action.action_id,
            basemap_id=(
                turn_contract.requested_basemap
                or basemap_id
                or self._infer_basemap_id(turn_contract)
            ),
            overlay_ids=self._infer_overlay_ids(
                turn_contract=turn_contract,
                resolved_location=resolved_location,
                existing_overlay_ids=overlay_ids,
            ),
        )
        request = self.request_builder.build_location_search_request(
            plan,
            resolved_location,
            turn_contract=turn_contract,
            active_visualization=(
                latest_memory.get("active_visualization")
                if isinstance(latest_memory, dict)
                else None
            ),
        )
        return await self.search_orchestrator.execute(request)

    # -------------------------------------------------------------------------
    def _infer_overlay_ids(
        self,
        *,
        turn_contract,
        resolved_location,
        existing_overlay_ids: list[str],
    ) -> list[str]:
        inferred = self.overlay_inference_service.infer_overlays(
            turn_contract=turn_contract,
            location=resolved_location,
            existing_overlay_ids=existing_overlay_ids,
        )
        merged = list(existing_overlay_ids)
        for overlay_id in inferred.overlay_ids:
            if overlay_id not in merged:
                merged.append(overlay_id)
        return merged

    # -------------------------------------------------------------------------
    @staticmethod
    def _infer_basemap_id(turn_contract) -> str | None:
        if turn_contract.requested_basemap:
            return turn_contract.requested_basemap
        haystack = " ".join(
            [
                turn_contract.user_text.lower(),
                turn_contract.normalized_action.action_id.lower(),
                *[item.lower() for item in turn_contract.normalized_action.task_tags],
                *[item.lower() for item in turn_contract.normalized_action.action_tags],
            ]
        )
        if any(marker in haystack for marker in ("satellite", "imagery", "true color")):
            return "esri_world_imagery"
        if any(marker in haystack for marker in ("street map", "street maps", "no satellite")):
            return "osm_default"
        if any(marker in haystack for marker in ("terrain", "elevation", "topography")):
            return "osm_terrain"
        return None
