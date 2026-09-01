from __future__ import annotations

from server.common.typing import is_json_object, json_array, json_object

from collections.abc import Callable
import asyncio
from time import monotonic
from typing import Any, cast
from uuid import uuid4

from server.common.logger import logger as LOGGER
from server.contracts.chat import (
    ChatTurnRequest,
    ChatTurnResponse,
    ContextUsageResponse,
)
from server.repositories.model_settings import ModelSettingsRepository
from server.repositories.conversations import ConversationRepository
from server.services.agent.agent_tool_catalog_service import AgentToolCatalogService
from server.services.agent.capability_resolver import CapabilityResolver
from server.domain.agent.decision import ClarificationRequest
from server.services.agent.direct_turn_response import DirectTurnResponseService
from server.services.agent.conversation_state import (
    ConversationTaskStateService,
)
from server.services.agent.location_memory import LocationMemoryService
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.agent.context_assembler import AgentContextAssembler
from server.domain.agent.context import ConversationDirective
from server.domain.agent.pipeline import VisualizationUpdate
from server.services.agent.native_tool_loop import (
    AgentExecutionContext,
    AgentToolLoopRequest,
    NativeToolLoop,
)
from server.services.agent.pipeline_router import DeterministicAgentRouter
from server.services.agent.parser_service import ParserService
from server.services.agent.policy_engine import PolicyEngine
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_history import AgentTurnHistoryService
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler
from server.services.agent.planned_turn_execution import PlannedTurnExecutionService
from server.services.agent.turn_support import AgentTurnSupport
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.tool_planner import DeterministicToolPlanner
from server.prompts.agent import build_native_agent_messages
from server.services.llm.types import LLMToolDefinition
from server.services.llm.context_profile_resolver import ModelContextProfileResolver
from server.services.chat.history_service import ChatHistoryService
from server.services.search.orchestrator import LocationSearchOrchestrator
from server.services.search.request_builder import RequestBuilder
from server.contracts.geospatial import MapSession


###############################################################################
class AgentOrchestrator:
    _compose_map_session_message = staticmethod(
        AgentResponseBuilder.compose_map_session_message
    )
    _compose_direct_tool_message = staticmethod(
        AgentResponseBuilder.compose_direct_tool_message
    )
    _has_parser_runtime_failure = staticmethod(
        AgentTurnSupport.has_parser_runtime_failure
    )

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
        native_tool_loop: NativeToolLoop,
        agent_tool_catalog_service: AgentToolCatalogService,
        settings_repo: ModelSettingsRepository,
        history_service: ChatHistoryService,
        conversation_repository: ConversationRepository,
        task_state_service: ConversationTaskStateService,
        pipeline_router: DeterministicAgentRouter,
        tool_planner: DeterministicToolPlanner,
        tool_plan_executor: ToolPlanExecutor,
        capability_resolver: CapabilityResolver,
        response_synthesizer: GroundedResponseSynthesizer,
        direct_turn_response_service: DirectTurnResponseService,
        context_profile_resolver: ModelContextProfileResolver | None = None,
    ) -> None:
        self.search_orchestrator = search_orchestrator
        self.parser_service = parser_service
        self.location_memory_service = location_memory_service
        self.policy_engine = policy_engine
        self.tool_registry = tool_registry
        self.request_builder = request_builder
        self.settings_repo = settings_repo
        self.agent_tool_catalog_service = agent_tool_catalog_service
        self.agent_tool_catalog_service.register_with(self.tool_registry)
        self.native_tool_loop = native_tool_loop
        self.history_service = history_service
        self.conversation_repository = conversation_repository
        self.task_state_service = task_state_service
        self.instruction_state_service = ConversationInstructionService()
        self._active_directives: dict[str, list[ConversationDirective]] = {}
        self.context_assembler = AgentContextAssembler(context_profile_resolver)
        self._context_packages: dict[str, Any] = {}
        self._persisted_context_state: dict[str, dict[str, Any]] = {}
        self.pipeline_router = pipeline_router
        self.tool_planner = tool_planner
        self.tool_plan_executor = tool_plan_executor
        self.capability_resolver = capability_resolver
        self.response_synthesizer = response_synthesizer
        self.direct_turn_response_service = direct_turn_response_service
        self.turn_history_service = AgentTurnHistoryService(
            history_service=self.history_service,
            location_memory_service=self.location_memory_service,
        )
        self.turn_state_assembler = AgentTurnStateAssembler(
            search_orchestrator=self.search_orchestrator,
            policy_engine=self.policy_engine,
            request_builder=self.request_builder,
            location_memory_service=self.location_memory_service,
            response_synthesizer=self.response_synthesizer,
            history_service=self.history_service,
            task_state_service=self.task_state_service,
        )
        self.planned_turn_execution_service = PlannedTurnExecutionService(
            tool_plan_executor=self.tool_plan_executor,
            task_state_service=self.task_state_service,
            turn_state_assembler=self.turn_state_assembler,
            response_synthesizer=self.response_synthesizer,
            instruction_state_service=self.instruction_state_service,
            active_directives=self._active_directives,
            history_service=self.history_service,
        )

    # -------------------------------------------------------------------------
    async def run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ChatTurnResponse:
        conversation_id = payload.conversation_id
        repository = self.conversation_repository
        persisted: dict[str, Any] | None = None
        directives: list[ConversationDirective] = []
        persisted = repository.read_state(conversation_id)
        self._persisted_context_state[conversation_id] = persisted
        self.task_state_service.hydrate(conversation_id, persisted.get("task_snapshot"))
        directives = [
            ConversationDirective.model_validate(item)
            for item in persisted.get("active_instructions", [])
        ]
        directives = self.instruction_state_service.apply_user_message(
            directives,
            payload.message,
            len(
                self.history_service.list_recent_messages(conversation_id, limit=10_000)
            )
            + 1,
        )
        self._active_directives[conversation_id] = directives
        response = await self._run_turn(payload, progress_callback)
        response = self._with_phase_usage(response)
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
        def numeric_value(item: dict[str, Any], key: str) -> int | None:
            value = item.get(key)
            if isinstance(value, bool):
                return None
            try:
                parsed = int(value)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None
            return parsed if parsed >= 0 else None

        def aggregate_optional(
            items: list[dict[str, Any]], key: str
        ) -> int | None:
            values = [numeric_value(item, key) for item in items]
            return sum(value for value in values if value is not None) if all(
                value is not None for value in values
            ) else None

        def phase_source(items: list[dict[str, Any]]) -> str:
            if not items:
                return "estimated"
            has_input = all(
                numeric_value(item, "reported_input_tokens") is not None
                for item in items
            )
            has_output = all(
                numeric_value(item, "reported_output_tokens") is not None
                for item in items
            )
            if has_input and has_output:
                return "provider_reported"
            if has_input or has_output:
                return "hybrid"
            return "estimated"

        def effective_input_value(item: dict[str, Any]) -> int:
            reported = numeric_value(item, "reported_input_tokens")
            if reported is not None:
                return reported
            return numeric_value(item, "estimated_input_tokens") or 0

        phases: dict[str, dict[str, Any]] = {}
        if response.context_usage is not None:
            phases["parser"] = response.context_usage.model_dump(
                mode="json", exclude={"phases"}
            )
        loop_usages = []
        if is_json_object(response.tool_payload):
            raw_loop_usages = response.tool_payload.get("context_usages")
            if isinstance(raw_loop_usages, list):
                loop_usages = [
                    item for item in raw_loop_usages if is_json_object(item)
                ]
        if loop_usages:
            native_phase: dict[str, Any] = {
                "iterations": loop_usages,
                "estimated_input_tokens": sum(
                    int(item.get("estimated_input_tokens") or 0) for item in loop_usages
                ),
                "reported_input_tokens": aggregate_optional(
                    loop_usages, "reported_input_tokens"
                ),
                "reported_output_tokens": aggregate_optional(
                    loop_usages, "reported_output_tokens"
                ),
                "usage_source": phase_source(loop_usages),
                "peak_request_tokens": max(
                    (effective_input_value(item) for item in loop_usages),
                ),
                "total_input_tokens": sum(
                    effective_input_value(item)
                    for item in loop_usages
                ),
                "total_output_tokens": aggregate_optional(
                    loop_usages, "reported_output_tokens"
                ),
            }
            first_loop_usage = loop_usages[0]
            for key in (
                "provider",
                "model",
                "selected_context_window",
                "model_context_limit",
                "usable_prompt_budget_tokens",
                "context_profile_source",
            ):
                if first_loop_usage.get(key) is not None:
                    native_phase[key] = first_loop_usage[key]
            for key in (
                "reserved_output_tokens",
                "tool_schema_tokens",
                "response_schema_tokens",
                "safety_margin_tokens",
            ):
                value = aggregate_optional(loop_usages, key)
                if value is not None:
                    native_phase[key] = value
            native_phase["compaction_applied"] = any(
                item.get("compaction_applied") is True for item in loop_usages
            )
            phases["native_loop"] = native_phase
        synthesis = getattr(self.response_synthesizer, "last_context_usage", None)
        if is_json_object(synthesis):
            phases["synthesis"] = synthesis
        base_usage = response.context_usage
        if base_usage is None:
            for candidate in phases.values():
                try:
                    base_usage = ContextUsageResponse.model_validate(candidate)
                except Exception:
                    continue
                break
        if base_usage is None and loop_usages:
            try:
                base_usage = ContextUsageResponse.model_validate(loop_usages[0])
            except Exception:
                base_usage = None
        if base_usage is None or not phases:
            return response

        inputs = [
            effective_input_value(item)
            for item in phases.values()
            if is_json_object(item)
        ]
        output_values = [
            numeric_value(item, "reported_output_tokens")
            for item in phases.values()
            if is_json_object(item)
            and numeric_value(item, "reported_output_tokens") is not None
        ]
        usage = base_usage.model_copy(
            update={
                "phases": phases,
                "peak_request_tokens": max(inputs, default=0),
                "total_input_tokens": sum(inputs),
                "usage_percent": (
                    round(
                        (max(inputs, default=0)
                         / max(base_usage.usable_prompt_budget_tokens, 1))
                        * 100,
                        1,
                    )
                    if base_usage.usable_prompt_budget_tokens is not None
                    else None
                ),
                "total_output_tokens": (
                    sum(output_values) if len(output_values) == len(phases) else None
                ),
            }
        )
        return response.model_copy(update={"context_usage": usage})

    # -------------------------------------------------------------------------
    async def _run_turn(
        self,
        payload: ChatTurnRequest,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> ChatTurnResponse:
        request_id = payload.request_id or f"chat-{uuid4().hex[:12]}"
        LOGGER.info(
            "chat_turn_start request_id=%s conversation_id=%s message_length=%s",
            request_id,
            payload.conversation_id,
            len(payload.message),
        )
        conversation_id = payload.conversation_id
        existing_response = self.turn_history_service.load_existing_response(
            conversation_id, request_id
        )
        if existing_response is not None:
            return existing_response
        if (
            self.history_service.find_message_by_request_id(
                conversation_id=conversation_id,
                role="user",
                request_id=request_id,
            )
            is None
        ):
            self.history_service.append_message(
                conversation_id=conversation_id,
                role="user",
                content=payload.message,
                request_id=request_id,
            )

        recent_messages = self.history_service.list_recent_messages(
            conversation_id, limit=200
        )
        for index in range(len(recent_messages) - 1, -1, -1):
            message = recent_messages[index]
            if (
                message.get("role") == "user"
                and message.get("content") == payload.message
            ):
                recent_messages.pop(index)
                break
        latest_contract = self.history_service.get_latest_turn_contract(conversation_id)
        latest_memory = self.history_service.get_latest_memory_snapshot(conversation_id)
        conversation_key = conversation_id
        state_before = self.task_state_service.snapshot(conversation_key)
        latest_memory = self.turn_history_service.merge_conversation_state_memory(
            latest_memory,
            state_before.active_map_session,
        )

        settings = self.settings_repo.get_required()
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

        parser_kwargs: dict[str, Any] = {
            "user_message": payload.message,
            "memory_snapshot": latest_memory,
            "conversation_messages": recent_messages,
        }
        parser_kwargs["active_instructions"] = [
            item.model_dump(mode="json")
            for item in self.instruction_state_service.active(
                self._active_directives.get(conversation_key, [])
            )
        ]
        parser_kwargs["task_snapshot"] = state_before.model_dump(mode="json")
        parser_run = None
        parser_usage: dict[str, object] | None = None
        parser_timeout_seconds = float(
            getattr(self.parser_service, "PARSER_TIMEOUT_SECONDS", 35.0)
        )
        parser_deadline = monotonic() + parser_timeout_seconds
        try:
            parse_with_usage = getattr(
                self.parser_service, "parse_turn_with_usage", None
            )
            if callable(parse_with_usage):
                parser_run = await asyncio.wait_for(
                    asyncio.to_thread(
                        parse_with_usage,
                        **parser_kwargs,
                        deadline_monotonic=parser_deadline,
                    ),
                    timeout=parser_timeout_seconds + 1.0,
                )
                turn_contract = parser_run.turn_contract
                parser_usage = parser_run.context_usage
            else:
                turn_contract = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.parser_service.parse_turn,
                        **parser_kwargs,
                    ),
                    timeout=parser_timeout_seconds + 1.0,
                )
        except asyncio.TimeoutError:
            LOGGER.warning(
                "parser_budget_exhausted request_id=%s provider=%s model=%s",
                request_id,
                settings.agent_model_provider,
                settings.agent_model_name,
            )
            turn_contract = self.parser_service.build_parser_failure_turn_result(
                user_message=payload.message,
                memory_snapshot=latest_memory,
                conversation_messages=recent_messages,
                provider_error={
                    "code": "parser_timeout",
                    "category": "provider_api",
                    "provider": settings.agent_model_provider,
                    "model": settings.agent_model_name,
                    "stage": "structured_intent_extraction",
                    "retryable": True,
                },
            )
        turn_contract = self.turn_history_service.merge_memory_location_signals(
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        turn_contract = self.capability_resolver.resolve(turn_contract)
        LOGGER.info(
            "chat_turn_parsed request_id=%s conversation_key=%s task=%s action=%s relationship=%s context_query=%s tools_needed=%s specialist_candidate=%s viewport_scope=%s basemap=%s layers=%s concepts=%s",
            request_id,
            conversation_key,
            turn_contract.task_class,
            turn_contract.normalized_action.action_id,
            turn_contract.relationship,
            turn_contract.context_query.kind,
            turn_contract.tools_needed,
            self.pipeline_router.select_specialist(turn_contract),
            turn_contract.viewport_intent.scope
            if turn_contract.viewport_intent is not None
            else None,
            turn_contract.requested_basemap,
            ",".join(turn_contract.requested_layers)
            if turn_contract.requested_layers
            else "-",
            ",".join(turn_contract.requested_concepts)
            if turn_contract.requested_concepts
            else "-",
        )
        if progress_callback is not None:
            progress_callback(
                "parsed",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
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
            bool(latest_memory.get("active_visualization"))
            if is_json_object(latest_memory)
            else False,
        )
        context_usage = (
            ContextUsageResponse.model_validate(parser_usage)
            if is_json_object(parser_usage)
            else None
        )
        preflight_decision = self.policy_engine.evaluate_preflight(turn_contract)
        direct_response = await self.direct_turn_response_service.handle(
            request_id=request_id,
            conversation_id=conversation_id,
            conversation_key=conversation_key,
            task=task,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
            latest_contract=latest_contract,
            recent_messages=recent_messages,
            context_usage=context_usage,
            preflight_decision=preflight_decision,
        )
        if direct_response is not None:
            return direct_response

        if (
            turn_contract.clarification_plan is not None
            and not turn_contract.requested_layers
        ):
            return await self.turn_state_assembler.build_partial_clarification_response(
                request_id=request_id,
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                context_usage=context_usage,
            )

        settings = self.settings_repo.get_required()
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
                    "conversation_id": conversation_id,
                    "specialist": specialist,
                    "planned_tools": list(tool_plan.selected_tools),
                },
            )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="routed",
            progress_summary=f"Routed to {specialist}.",
            tool_plan=tool_plan.model_dump(mode="json"),
        )
        constraints = self.policy_engine.build_agent_constraints(
            turn_contract,
            latest_memory,
        )
        native_context = AgentExecutionContext(
            request_id=request_id,
            conversation_id=conversation_id,
            parsed_request=turn_contract.model_dump(mode="json"),
            map_state=json_object(latest_memory),
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
                "complexity": (
                    "simple"
                    if not turn_contract.atomic_tasks
                    and len(tool_plan.steps) <= 1
                    and not turn_contract.required_data_sources
                    else "complex"
                ),
            },
        )
        deterministic_tools_available = (
            bool(tool_plan.steps) or bool(tool_plan.visualization_update)
        ) and all(
            self.tool_registry.has_native_tool(step.tool_name)
            for step in tool_plan.steps
        )
        if deterministic_tools_available:
            return await self.planned_turn_execution_service.execute(
                request_id=request_id,
                conversation_id=conversation_id,
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
        build_native_tools = getattr(
            self.agent_tool_catalog_service, "build_native_tools", None
        )
        native_tools: list[LLMToolDefinition]
        if callable(build_native_tools):
            native_tools = cast(
                Callable[[AgentExecutionContext], list[LLMToolDefinition]],
                build_native_tools,
            )(native_context)
        else:
            native_tools = self.tool_registry.list_native_tools()
        tool_loop_result = await self.native_tool_loop.run(
            AgentToolLoopRequest(
                provider=settings.agent_model_provider,
                model=settings.agent_model_name,
                messages=build_native_agent_messages(
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
            "failure_category": tool_loop_result.failure_category,
            "failure_detail": tool_loop_result.failure_detail,
            "context_usages": tool_loop_result.context_usages,
        }
        map_result = await self.turn_state_assembler.build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if isinstance(map_result, ClarificationRequest) and (
            tool_loop_result.failure_category is None
        ):
            return await self.turn_state_assembler.build_location_clarification_response(
                request_id=request_id,
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                context_usage=None,
                clarification=map_result,
                tool_payload=tool_payload,
            )
        map_session = map_result if isinstance(map_result, MapSession) else None
        if map_session is None:
            map_session = tool_loop_result.map_session
        overlay_mutation_results = []
        if map_session is None and turn_contract.overlay_commands:
            # A visibility/removal follow-up can be resolved entirely against
            # the active collection even when a native adapter did not return
            # another map payload.
            active_raw = latest_memory.get("active_visualization")
            if is_json_object(active_raw):
                try:
                    map_session, overlay_mutation_results = (
                        self.turn_state_assembler.apply_overlay_commands(
                            MapSession.model_validate(active_raw),
                            list(turn_contract.overlay_commands),
                        )
                    )
                except Exception:
                    LOGGER.warning(
                        "Could not apply native-loop overlay mutation to active map",
                        exc_info=True,
                    )
        direct_result = (
            self.turn_state_assembler.extract_direct_result_from_tool_results(
                tool_payload
            )
        )
        capability_selection = (
            self.turn_state_assembler.extract_capability_selection_from_tool_results(
                tool_payload
            )
        )
        if map_session is None and capability_selection is not None:
            map_result = await self.turn_state_assembler.build_map_session_from_capability_selection(
                capability_selection=capability_selection,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
            )
            if isinstance(map_result, ClarificationRequest) and (
                tool_loop_result.failure_category is None
            ):
                return await self.turn_state_assembler.build_location_clarification_response(
                    request_id=request_id,
                    conversation_id=conversation_id,
                    conversation_key=conversation_key,
                    task=task,
                    turn_contract=turn_contract,
                    latest_memory=latest_memory,
                    context_usage=None,
                    clarification=map_result,
                    tool_payload=tool_payload,
                )
            map_session = map_result if isinstance(map_result, MapSession) else None
        if (
            map_session is not None
            and turn_contract.overlay_commands
            and not overlay_mutation_results
        ):
            map_session, overlay_mutation_results = (
                self.turn_state_assembler.apply_overlay_commands(
                    map_session,
                    list(turn_contract.overlay_commands),
                )
            )
        self.turn_state_assembler.append_provider_events(tool_payload, map_session)
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
            require_verified_result=(
                turn_contract.task_class == "map_search"
                and turn_contract.context_query.kind == "none"
            ),
        )
        operation = AgentResponseBuilder.build_verified_operation_result(
            assistant_message=assistant_message,
            map_session=map_session,
            direct_result=direct_result,
            tool_payload=tool_payload,
            user_text=turn_contract.user_text,
            is_capability_question=turn_contract.context_query.kind == "capabilities",
            require_verified_result=(
                turn_contract.task_class == "map_search"
                and turn_contract.context_query.kind == "none"
            ),
        )
        if tool_loop_result.failure_category is not None:
            operation = operation.model_copy(
                update={
                    "kind": "error",
                    "status": "failed",
                    "failure_category": tool_loop_result.failure_category,
                    "provider_error": {
                        "category": tool_loop_result.failure_category,
                        "detail": tool_loop_result.failure_detail,
                        "stage": "native_tool_loop",
                    },
                }
            )
        # Persist the verified execution state before asking the language
        # model to phrase it.  Otherwise the synthesis evidence can contain
        # the pre-execution task graph and contradict a completed map.
        synthesis_failure = self.turn_state_assembler.failure_from_operation(
            operation, tool_payload
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="failed" if synthesis_failure is not None else "completed",
            progress_summary=operation.message,
            failure=synthesis_failure,
            tool_plan=tool_plan.model_dump(mode="json"),
            tool_result_refs=[
                str(item.get("tool_call_id"))
                for item in json_array(tool_payload.get("tool_results"))
                if is_json_object(item) and item.get("tool_call_id")
            ],
        )
        self.task_state_service.set_active_visualization(
            conversation_key, map_session, tool_payload=tool_payload
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
        synthesis_category = getattr(
            self.response_synthesizer, "last_failure_category", None
        )
        operation = operation.model_copy(
            update={
                "message": assistant_message,
                "warnings": [
                    *operation.warnings,
                    *(
                        [
                            "Grounded response synthesis failed; the verified response was retained. "
                            f"Category: {synthesis_category}."
                        ]
                        if synthesis_category
                        else []
                    ),
                ],
                # A synthesis failure does not invalidate a verified map/tool
                # operation. Keep the operation successful and surface the
                # categorized synthesis warning separately.
                "failure_category": (
                    None
                    if operation.status == "success"
                    else synthesis_category or operation.failure_category
                ),
            }
        )
        decision = AgentResponseBuilder.build_final_decision(
            action_id=turn_contract.normalized_action.action_id,
            operation=operation,
            trace_steps=decision_trace_steps,
        )
        failure = self.turn_state_assembler.failure_from_operation(
            operation, tool_payload
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="failed" if failure is not None else "completed",
            progress_summary=operation.message,
            failure=failure,
            tool_plan=tool_plan.model_dump(mode="json"),
            tool_result_refs=[
                str(item.get("tool_call_id"))
                for item in json_array(tool_payload.get("tool_results"))
                if is_json_object(item) and item.get("tool_call_id")
            ],
        )
        self.task_state_service.set_active_visualization(
            conversation_key, map_session, tool_payload=tool_payload
        )

        mutation_added = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.added_instance_ids
        ]
        mutation_removed = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.removed_instance_ids
        ]
        mutation_updated = sorted(
            {
                instance_id
                for result in overlay_mutation_results
                for instance_id in result.updated_instance_ids
            }
        )
        mutation_unmatched = [
            selector
            for result in overlay_mutation_results
            for selector in result.unmatched_selectors
        ]
        mutation_ambiguous = [
            selector
            for result in overlay_mutation_results
            for selector in result.ambiguous_selectors
        ]
        visualization_update = VisualizationUpdate(
            add_layer_ids=mutation_added
            if turn_contract.overlay_commands
            else list(turn_contract.requested_layers),
            remove_layer_ids=mutation_removed,
            collection_revision=(
                map_session.overlay_collection.revision
                if map_session is not None
                else None
            ),
            added_instance_ids=mutation_added,
            removed_instance_ids=mutation_removed,
            updated_instance_ids=mutation_updated,
            unmatched_selectors=mutation_unmatched,
            ambiguous_selectors=mutation_ambiguous,
            clarification=next(
                (
                    result.clarification
                    for result in overlay_mutation_results
                    if result.clarification
                ),
                None,
            ),
        )

        self.history_service.append_message(
            conversation_id=conversation_id,
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
            map_session=map_session.model_dump(mode="json")
            if map_session is not None
            else None,
        )

        LOGGER.info(
            "chat_turn_complete request_id=%s conversation_id=%s state=%s",
            request_id,
            conversation_id,
            decision.plan.state,
        )
        return ChatTurnResponse(
            request_id=request_id,
            conversation_id=conversation_id,
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
