from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server.common.logger import logger as LOGGER
from server.domain.agent.context import ConversationDirective
from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import (
    ConversationTaskRecord,
    ToolPlan,
    VisualizationUpdate,
)
from server.contracts.chat import ChatOperationResult, ChatTurnResponse
from server.contracts.extraction import TurnParseResult
from server.contracts.geospatial import MapSession, OverlayMutationResult
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler
from server.services.agent.tool_plan_executor import ToolPlanExecutor
from server.services.agent.overlay_collection import OverlayCollectionService
from server.services.chat.history_service import ChatHistoryService

ProgressCallback = Callable[[str, dict[str, Any]], None]


###############################################################################
class PlannedTurnExecutionService:
    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        tool_plan_executor: ToolPlanExecutor,
        task_state_service: ConversationTaskStateService,
        turn_state_assembler: AgentTurnStateAssembler,
        response_synthesizer: GroundedResponseSynthesizer,
        instruction_state_service: ConversationInstructionService,
        active_directives: dict[str, list[ConversationDirective]],
        history_service: ChatHistoryService,
    ) -> None:
        self.tool_plan_executor = tool_plan_executor
        self.task_state_service = task_state_service
        self.turn_state_assembler = turn_state_assembler
        self.response_synthesizer = response_synthesizer
        self.instruction_state_service = instruction_state_service
        self.active_directives = active_directives
        self.history_service = history_service

    # -------------------------------------------------------------------------
    @staticmethod
    def _active_map_session(latest_memory: dict[str, Any]) -> MapSession | None:
        raw = latest_memory.get("active_visualization")
        if not isinstance(raw, dict):
            return None
        try:
            return MapSession.model_validate(raw)
        except Exception:
            LOGGER.warning(
                "Ignoring invalid active map session while applying overlay command"
            )
            return None

    # -------------------------------------------------------------------------
    @classmethod
    def _apply_overlay_commands(
        cls,
        session: MapSession,
        turn_contract: TurnParseResult,
        *,
        state_session: MapSession | None = None,
    ) -> tuple[MapSession, list[OverlayMutationResult]]:
        return AgentTurnStateAssembler.apply_overlay_commands(
            session,
            list(turn_contract.overlay_commands),
            state_session=state_session,
        )

    # -------------------------------------------------------------------------
    @staticmethod
    def _is_local_overlay_mutation(
        turn_contract: TurnParseResult,
        latest_memory: dict[str, Any],
    ) -> bool:
        active_map = PlannedTurnExecutionService._active_map_session(latest_memory)
        if not turn_contract.overlay_commands or active_map is None:
            return False
        collection = OverlayCollectionService.from_map_session(active_map)
        current_view = active_map.viewport.model_dump(mode="json")
        for command in turn_contract.overlay_commands:
            if command.action in {"remove", "keep_only", "hide"}:
                continue
            if command.action in {
                "show",
                "update",
            } and not OverlayCollectionService.has_matching_instances(
                collection,
                command,
                current_view=current_view,
            ):
                # An absent show/update target may need a catalog lookup or
                # provider fetch. Let the normal plan build that map.
                return False
            if command.action == "show":
                continue
            if (
                command.action == "update"
                and command.patch.time is None
                and command.patch.style is None
                and command.patch.format is None
            ):
                continue
            return False
        return True

    # -------------------------------------------------------------------------
    async def execute(
        self,
        *,
        request_id: str,
        conversation_id: str,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract: TurnParseResult,
        latest_memory: dict[str, Any],
        latest_contract: dict[str, Any] | None,
        context_usage: Any,
        native_context: AgentExecutionContext,
        tool_plan: ToolPlan,
        progress_callback: ProgressCallback | None = None,
    ) -> ChatTurnResponse:
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="in_progress",
            progress_summary="Executing validated tool plan.",
            tool_plan=tool_plan.model_dump(mode="json"),
        )
        local_overlay_mutation = self._is_local_overlay_mutation(
            turn_contract,
            latest_memory,
        )
        overlay_mutation_results: list[OverlayMutationResult] = []
        map_session: MapSession | None = None
        local_map_session = self._active_map_session(latest_memory)
        if local_overlay_mutation and local_map_session is not None:
            map_session, overlay_mutation_results = self._apply_overlay_commands(
                local_map_session,
                turn_contract,
            )
            planned_results = []
        else:
            planned_results = await self.tool_plan_executor.execute(
                tool_plan,
                native_context,
                on_tool_started=(
                    lambda step: (
                        progress_callback(
                            "tool_call_started",
                            {
                                "request_id": request_id,
                                "conversation_id": conversation_id,
                                "tool_call_id": step.step_id,
                                "name": step.tool_name,
                            },
                        )
                        if progress_callback is not None
                        else None
                    )
                ),
                on_tool_completed=(
                    lambda result: (
                        progress_callback(
                            "tool_call_completed",
                            {
                                "request_id": request_id,
                                "conversation_id": conversation_id,
                                "tool_call_id": result.step_id,
                                "name": result.provenance.tool_name,
                                "ok": result.ok,
                                "error": result.error_message,
                            },
                        )
                        if progress_callback is not None
                        else None
                    )
                ),
            )
        tool_payload: dict[str, Any] = {
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
                            {"code": result.error_code, "message": result.error_message}
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
                step.required
                for step in tool_plan.steps
                if step.step_id == result.step_id
            )
        ]
        if not local_overlay_mutation:
            map_session = await self.turn_state_assembler.build_combined_map_session_from_tool_results(
                tool_payload=tool_payload,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
            )
            if map_session is None and tool_plan.visualization_update:
                map_session = await self.turn_state_assembler.build_map_session_from_turn_contract(
                    turn_contract, latest_memory
                )
            if map_session is not None and turn_contract.overlay_commands:
                active_state_session = self._active_map_session(latest_memory)
                map_session, overlay_mutation_results = self._apply_overlay_commands(
                    map_session,
                    turn_contract,
                    state_session=active_state_session,
                )
        self.turn_state_assembler.append_provider_events(tool_payload, map_session)
        mutation_clarification = next(
            (
                result.clarification
                for result in overlay_mutation_results
                if result.clarification
            ),
            None,
        )
        direct_result = (
            self.turn_state_assembler.extract_direct_result_from_tool_results(
                tool_payload
            )
        )
        if required_failures and map_session is None and direct_result is None:
            assistant_message = (
                required_failures[0].error_message
                or "The required geospatial tool failed."
            )
            operation = ChatOperationResult(
                kind="error", status="failed", message=assistant_message
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
                kind="error", status="failed", message=assistant_message
            )
        else:
            assistant_message = AgentResponseBuilder.build_verified_assistant_message(
                "",
                map_session=map_session,
                direct_result=direct_result,
                tool_payload=tool_payload,
                require_verified_result=turn_contract.task_class == "map_search",
            )
            operation = AgentResponseBuilder.build_verified_operation_result(
                assistant_message=assistant_message,
                map_session=map_session,
                direct_result=direct_result,
                tool_payload=tool_payload,
                user_text=turn_contract.user_text,
                is_capability_question=False,
                require_verified_result=turn_contract.task_class == "map_search",
            )
            if (
                any(not result.ok for result in planned_results)
                and operation.status == "success"
            ):
                operation = operation.model_copy(update={"status": "partial"})
            if turn_contract.clarification_plan is not None:
                operation = operation.model_copy(update={"status": "partial"})
            if mutation_clarification:
                operation = operation.model_copy(
                    update={
                        "status": "partial",
                        "warnings": [*operation.warnings, mutation_clarification],
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
                tool_result_refs=[result.step_id for result in planned_results],
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
                clarification_plan=turn_contract.clarification_plan,
                task_status="completed" if operation.status == "success" else "partial",
                active_instructions=[
                    item.model_dump(mode="json")
                    for item in self.instruction_state_service.active(
                        self.active_directives.get(conversation_key, [])
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
                    "failure_category": synthesis_category
                    or operation.failure_category,
                }
            )
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
            tool_result_refs=[result.step_id for result in planned_results],
        )
        self.task_state_service.set_active_visualization(
            conversation_key, map_session, tool_payload=tool_payload
        )
        added_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.added_instance_ids
        ]
        removed_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.removed_instance_ids
        ]
        updated_instance_ids = [
            instance_id
            for result in overlay_mutation_results
            for instance_id in result.updated_instance_ids
        ]
        unmatched_selectors = [
            selector
            for result in overlay_mutation_results
            for selector in result.unmatched_selectors
        ]
        ambiguous_selectors = [
            selector
            for result in overlay_mutation_results
            for selector in result.ambiguous_selectors
        ]
        mutation_clarification = next(
            (
                result.clarification
                for result in overlay_mutation_results
                if result.clarification
            ),
            None,
        )
        visualization_update = VisualizationUpdate(
            basemap_replacement=(
                tool_plan.visualization_update.get("basemap_replacement")
                if isinstance(
                    tool_plan.visualization_update.get("basemap_replacement"), str
                )
                else turn_contract.requested_basemap
            ),
            add_layer_ids=(
                added_instance_ids
                if turn_contract.overlay_commands
                else list(turn_contract.requested_layers)
            ),
            remove_layer_ids=removed_instance_ids,
            collection_revision=(
                map_session.overlay_collection.revision
                if map_session is not None
                else None
            ),
            added_instance_ids=added_instance_ids,
            removed_instance_ids=removed_instance_ids,
            updated_instance_ids=sorted(set(updated_instance_ids)),
            unmatched_selectors=unmatched_selectors,
            ambiguous_selectors=ambiguous_selectors,
            clarification=mutation_clarification,
        )
        if progress_callback is not None and map_session is not None:
            progress_callback(
                "map_session_created",
                {
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "map_session": map_session.model_dump(mode="json"),
                },
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
            map_session=map_session.model_dump(mode="json") if map_session else None,
        )
        LOGGER.info(
            "planned_chat_turn_complete request_id=%s conversation_id=%s state=%s",
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
