from __future__ import annotations

from server.common.typing import is_json_object

from typing import Any

from server.domain.agent.decision import PolicyDecision
from server.domain.agent.pipeline import ConversationTaskRecord, TaskFailureDetail
from server.contracts.chat import ChatOperationResult, ChatTurnResponse
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.response_builder import AgentResponseBuilder
from server.services.agent.response_synthesizer import GroundedResponseSynthesizer
from server.services.agent.turn_support import AgentTurnSupport
from server.services.chat.history_service import ChatHistoryService

###############################################################################
class DirectTurnResponseService:

    # -------------------------------------------------------------------------
    @staticmethod
    def _parser_failure_message(
        turn_contract: Any,
        provider_error: dict[str, Any] | None,
    ) -> tuple[str, str]:
        category = str(
            getattr(turn_contract, "failure_category", None)
            or (provider_error or {}).get("category")
            or "provider_api"
        )
        details = str((provider_error or {}).get("detail") or "").strip()
        suffix = f" Detail: {details}" if details else ""
        messages = {
            "model_capability": (
                "The selected provider explicitly rejected the requested model capability "
                "during structured extraction. Verify that structured output is enabled for "
                "this model or provider."
            ),
            "provider_api": (
                "The agent provider failed while processing structured extraction. Check the "
                "provider connection, credentials, rate limits, or transient service status."
            ),
            "schema_definition": (
                "AEGIS rejected an invalid structured-output schema or tool definition before "
                "sending the request. This is an application schema issue, not a model choice issue."
            ),
            "response_parsing": (
                "The selected model responded, but its structured payload did not match the "
                "AEGIS extraction schema. A same-model schema-correction retry was attempted."
            ),
            "context_limit": (
                "The request exceeded the selected model's usable context budget. Shorten the "
                "current turn or let AEGIS compact older conversation context."
            ),
        }
        return messages.get(category, messages["provider_api"]) + suffix, category

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
        deterministic_context_question = AgentTurnSupport.is_deterministic_context_question(
            turn_contract.user_text
        )
        if (
            AgentTurnSupport.has_parser_authentication_failure(turn_contract)
            and not deterministic_context_question
        ):
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
                failure_category="provider_api",
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

        if (
            AgentTurnSupport.has_parser_runtime_failure(turn_contract)
            and not deterministic_context_question
        ):
            provider_error = getattr(turn_contract, "provider_error", None)
            provider_error_object = provider_error if is_json_object(provider_error) else None
            assistant_message, failure_category = self._parser_failure_message(
                turn_contract,
                provider_error_object,
            )
            failure = TaskFailureDetail(
                stage="structured_intent_extraction",
                component="agent_model",
                sanitized_error=(
                    str((provider_error_object or {}).get("detail") or "Structured extraction failed.")
                ),
                recovery_suggestion=(
                    "Review the categorized diagnostic and retry the same model after correcting the provider, schema, or context issue."
                ),
                user_explanation=assistant_message,
                provider_error=getattr(turn_contract, "provider_error", None),
                failure_category=failure_category,  # type: ignore[arg-type]
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
            or deterministic_context_question
        ):
            fallback_message = AgentTurnSupport.compose_general_question_message(
                turn_contract.user_text,
                recent_messages,
                latest_memory,
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
            failure_category=failure.failure_category,
            provider_error=failure.provider_error,
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
