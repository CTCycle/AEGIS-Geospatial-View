from __future__ import annotations

from collections.abc import Callable
from typing import Any

from server.common.logger import logger as LOGGER
from server.domain.agent.context import ConversationDirective
from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.pipeline import ConversationTaskRecord, ToolPlan, VisualizationUpdate
from server.domain.chat import ChatOperationResult, ChatTurnResponse
from server.domain.extraction.models import TurnParseResult
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.instruction_state import ConversationInstructionService
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_state_assembler import AgentTurnStateAssembler
from server.services.agent.tool_plan_executor import ToolPlanExecutor
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
                        "conversation_id": conversation_id,
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
                        "conversation_id": conversation_id,
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
        tool_payload: dict[str, Any] = {
            "tool_plan": tool_plan.model_dump(mode="json"),
            "tool_calls": [
                {
                    "id": result.step_id,
                    "name": result.provenance.tool_name,
                    "arguments": next(
                        step.arguments for step in tool_plan.steps if step.step_id == result.step_id
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
            and next(step.required for step in tool_plan.steps if step.step_id == result.step_id)
        ]
        map_session = await self.turn_state_assembler.build_combined_map_session_from_tool_results(
            tool_payload=tool_payload,
            turn_contract=turn_contract,
            latest_memory=latest_memory,
        )
        if map_session is None and tool_plan.visualization_update:
            map_session = await self.turn_state_assembler.build_map_session_from_turn_contract(
                turn_contract, latest_memory
            )
        direct_result = self.turn_state_assembler.extract_direct_result_from_tool_results(tool_payload)
        if required_failures and map_session is None and direct_result is None:
            assistant_message = required_failures[0].error_message or "The required geospatial tool failed."
            operation = ChatOperationResult(kind="error", status="failed", message=assistant_message)
        elif turn_contract.task_class == "map_search" and map_session is None and direct_result is None:
            assistant_message = (
                "I could not create a map session from this request. "
                "Try a more specific place name or choose an available map layer."
            )
            operation = ChatOperationResult(kind="error", status="failed", message=assistant_message)
        else:
            assistant_message = AgentResponseBuilder.build_verified_assistant_message(
                "", map_session=map_session, direct_result=direct_result, tool_payload=tool_payload
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
                task_status="completed" if operation.status == "success" else "partial",
                active_instructions=[
                    item.model_dump(mode="json")
                    for item in self.instruction_state_service.active(
                        self.active_directives.get(conversation_key, [])
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
            basemap_replacement=(
                tool_plan.visualization_update.get("basemap_replacement")
                if isinstance(tool_plan.visualization_update.get("basemap_replacement"), str)
                else turn_contract.requested_basemap
            ),
            add_layer_ids=list(turn_contract.requested_layers),
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
