from __future__ import annotations

from server.common.typing import is_json_object

from typing import Any

from server.domain.agent.decision import PolicyDecision
from server.domain.agent.pipeline import ConversationTaskRecord, TaskFailureDetail
from server.domain.chat import ChatOperationResult, ChatTurnResponse
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_support import AgentTurnSupport
from server.services.chat.history_service import ChatHistoryService

###############################################################################
class DirectTurnResponseService:

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        task_state_service: ConversationTaskStateService,
        history_service: ChatHistoryService,
        response_synthesizer: GroundedResponseSynthesizer,
    ) -> None:
        self.task_state_service = task_state_service
        self.history_service = history_service
        self.response_synthesizer = response_synthesizer

    # -------------------------------------------------------------------------
    async def handle(
        self,
        *,
        request_id: str,
        conversation_id: str,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract: Any,
        latest_memory: dict[str, Any],
        latest_contract: Any,
        recent_messages: list[dict[str, Any]],
        context_usage: Any,
        preflight_decision: PolicyDecision | None = None,
    ) -> ChatTurnResponse | None:
        if AgentTurnSupport.has_parser_authentication_failure(turn_contract):
            assistant_message = (
                "I could not use the configured agent model because the saved API key was rejected. "
                "Open Model Settings and replace the key before using that cloud model."
            )
            failure = TaskFailureDetail(
                stage="structured_intent_extraction",
                component="agent_model",
                sanitized_error="The configured agent credential was rejected.",
                recovery_suggestion="Replace the saved agent API key in Model Settings.",
                user_explanation=assistant_message,
                provider_error=getattr(turn_contract, "provider_error", None),
            )
            return self._persist_failure_response(
                request_id=request_id,
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                latest_contract=latest_contract,
                context_usage=context_usage,
                assistant_message=assistant_message,
                failure=failure,
                progress_summary="Intent extraction failed.",
            )

        if AgentTurnSupport.has_parser_runtime_failure(turn_contract):
            provider_error = getattr(turn_contract, "provider_error", None)
            if is_json_object(provider_error) and provider_error.get("code") == "provider_model_incompatible":
                assistant_message = (
                    f"OpenCode Go rejected the selected model during structured intent extraction "
                    f"(HTTP {provider_error.get('http_status') or 400}). Choose a compatible structured-output model and retry."
                )
            else:
                assistant_message = (
                    "I could not process this request because the configured agent model could not perform structured extraction. "
                    "Open Model Settings, choose an agent model that supports structured output and tool calling, or retry when the provider is available."
                )
            failure = TaskFailureDetail(
                stage="structured_intent_extraction",
                component="agent_model",
                sanitized_error="The configured agent model could not perform structured extraction.",
                recovery_suggestion="Open Model Settings, choose an agent model that supports structured output and tool calling, or refresh/pull the configured Ollama model.",
                user_explanation=assistant_message,
                provider_error=getattr(turn_contract, "provider_error", None),
            )
            return self._persist_failure_response(
                request_id=request_id,
                conversation_id=conversation_id,
                conversation_key=conversation_key,
                task=task,
                turn_contract=turn_contract,
                latest_memory=latest_memory,
                latest_contract=latest_contract,
                context_usage=context_usage,
                assistant_message=assistant_message,
                failure=failure,
                progress_summary="Intent extraction failed.",
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
            decision = AgentTurnSupport.build_direct_reject_decision(
                turn_contract.normalized_action.action_id
            )
            self.task_state_service.update_task(
                conversation_key,
                task.task_id,
                status="completed",
                progress_summary="Explained the latest captured failure.",
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
                    "memory_snapshot": latest_memory,
                    "request_id": request_id,
                },
            )
            return ChatTurnResponse(
                request_id=request_id,
                conversation_id=conversation_id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=decision,
                operation=operation,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
                failure_diagnostic=failure,
            )

        if (
            turn_contract.task_class == "general_question"
            or AgentTurnSupport.is_capability_question(turn_contract.user_text)
        ):
            fallback_message = AgentTurnSupport.compose_general_question_message(
                turn_contract.user_text,
                recent_messages,
            )
            operation = ChatOperationResult(
                kind=(
                    "capability_catalog"
                    if AgentTurnSupport.is_capability_question(turn_contract.user_text)
                    else "direct_answer"
                ),
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
                conversation_id=conversation_id,
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
                conversation_id=conversation_id,
                assistant_message=assistant_message,
                turn_contract=turn_contract,
                decision=AgentTurnSupport.build_direct_reject_decision(
                    turn_contract.normalized_action.action_id
                ),
                operation=operation,
                tool_payload=None,
                map_session=None,
                memory_snapshot=latest_memory,
                context_usage=context_usage,
                task_snapshot=self.task_state_service.snapshot(conversation_key),
            )

        if preflight_decision is None:
            return None

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
            status=(
                "needs_clarification"
                if preflight_decision.plan.state == "clarify"
                else "failed"
            ),
            blocking_ambiguity=(
                assistant_message
                if preflight_decision.plan.state == "clarify"
                else None
            ),
            progress_summary=assistant_message,
        )
        self.history_service.append_message(
            conversation_id=conversation_id,
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
            conversation_id=conversation_id,
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

    # -------------------------------------------------------------------------
    def _persist_failure_response(
        self,
        *,
        request_id: str,
        conversation_id: str,
        conversation_key: str,
        task: ConversationTaskRecord,
        turn_contract: Any,
        latest_memory: dict[str, Any],
        latest_contract: Any,
        context_usage: Any,
        assistant_message: str,
        failure: TaskFailureDetail,
        progress_summary: str,
    ) -> ChatTurnResponse:
        decision = AgentTurnSupport.build_direct_reject_decision(
            turn_contract.normalized_action.action_id
        )
        operation = ChatOperationResult(
            kind="error",
            status="failed",
            message=assistant_message,
        )
        self.task_state_service.update_task(
            conversation_key,
            task.task_id,
            status="failed",
            failure=failure,
            progress_summary=progress_summary,
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
                "memory_snapshot": latest_memory,
                "previous_turn_contract": latest_contract,
                "request_id": request_id,
            },
            tool_payload=None,
            map_session=None,
        )
        return ChatTurnResponse(
            request_id=request_id,
            conversation_id=conversation_id,
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
