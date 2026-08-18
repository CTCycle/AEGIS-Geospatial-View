from __future__ import annotations

from tests.conftest import run_async_in_thread
from typing import Any

from server.domain.agent.decision import ClarificationRequest, DecisionTrace, ExecutionPlan, PolicyDecision
from server.domain.agent.pipeline import ConversationTaskRecord, TaskFailureDetail
from server.domain.chat import ChatOperationResult
from server.domain.extraction.models import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.services.agent.conversation_state import ConversationTaskStateService
from server.services.agent.direct_turn_response import DirectTurnResponseService

###############################################################################
class _History:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    # -------------------------------------------------------------------------
    def append_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)

###############################################################################
class _Synthesizer:

    # -------------------------------------------------------------------------
    def synthesize(self, *, fallback_text: str, **_: Any) -> str:
        return f"synthesized: {fallback_text}"

###############################################################################
def _turn(
    *,
    user_text: str = "help",
    task_class: str = "general_question",
    relationship: str = "new_task",
    ambiguities: list[str] | None = None,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=user_text,
        conversation_context=ConversationContextSnapshot(),
        task_class=task_class,  # type: ignore[arg-type]
        normalized_action=NormalizedAction(
            action_id="help",
            action_label="Help",
            requires_location=False,
        ),
        relationship=relationship,  # type: ignore[arg-type]
        ambiguities=ambiguities or [],
    )

###############################################################################
def _task(state: ConversationTaskStateService, turn: TurnParseResult) -> ConversationTaskRecord:
    return state.start_task("conversation", turn, "direct_chat")

###############################################################################
def _service() -> tuple[DirectTurnResponseService, ConversationTaskStateService, _History]:
    state = ConversationTaskStateService()
    history = _History()
    return (
        DirectTurnResponseService(
            task_state_service=state,
            history_service=history,  # type: ignore[arg-type]
            response_synthesizer=_Synthesizer(),  # type: ignore[arg-type]
        ),
        state,
        history,
    )

###############################################################################
def test_parser_authentication_failure_persists_stable_failure_response() -> None:
    async def _run() -> None:
        service, state, history = _service()
        turn = _turn(ambiguities=["parser_authentication_failed"])
        response = await service.handle(
            request_id="request-1",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={},
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.operation == ChatOperationResult(
            kind="error",
            status="failed",
            message=response.assistant_message,
        )
        assert response.failure_diagnostic is not None
        assert history.messages[-1]["content"] == response.assistant_message
        assert response.task_snapshot is not None
        assert response.task_snapshot.tasks[-1].status == "failed"

    run_async_in_thread(_run())

###############################################################################
def test_provider_authentication_failure_persists_stable_failure_response() -> None:
    async def _run() -> None:
        service, state, history = _service()
        turn = _turn(
            user_text="Show Rome",
            task_class="map_search",
            ambiguities=["provider_authentication_failed"],
        )
        response = await service.handle(
            request_id="request-provider-auth",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={},
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.operation == ChatOperationResult(
            kind="error",
            status="failed",
            message=response.assistant_message,
        )
        assert "saved API key was rejected" in response.assistant_message
        assert response.failure_diagnostic is not None
        assert history.messages[-1]["content"] == response.assistant_message

    run_async_in_thread(_run())

###############################################################################
def test_failure_inquiry_explains_the_latest_structured_failure() -> None:
    async def _run() -> None:
        service, state, _ = _service()
        failed_turn = _turn(user_text="previous", task_class="map_search")
        failed_task = _task(state, failed_turn)
        state.update_task(
            "conversation",
            failed_task.task_id,
            status="failed",
            failure=TaskFailureDetail(
                stage="tool_execution",
                sanitized_error="Provider unavailable",
                user_explanation="The provider was unavailable.",
                recovery_suggestion="Try again later.",
            ),
        )
        inquiry = _turn(
            user_text="Why did the previous request fail?",
            relationship="failure_inquiry",
        )
        response = await service.handle(
            request_id="request-2",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, inquiry),
            turn_contract=inquiry,
            latest_memory={},
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.operation is not None
        assert response.operation.kind == "failure_diagnostic"
        assert response.operation.status == "success"
        assert "Try again later." in response.assistant_message

    run_async_in_thread(_run())

###############################################################################
def test_preflight_clarification_is_persisted_as_partial_response() -> None:
    async def _run() -> None:
        service, state, history = _service()
        turn = _turn(user_text="show weather", task_class="map_search")
        decision = PolicyDecision(
            plan=ExecutionPlan(
                state="clarify",
                mode="direct_text",
                action_id="weather",
            ),
            clarification=ClarificationRequest(
                question="Which location should I use?",
                reason="A location is required.",
                missing_fields=["location"],
            ),
            trace=DecisionTrace(steps=["location_required"]),
        )
        response = await service.handle(
            request_id="request-3",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={},
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
            preflight_decision=decision,
        )

        assert response is not None
        assert response.operation is not None
        assert response.operation.kind == "clarification"
        assert response.operation.status == "partial"
        assert response.assistant_message == "synthesized: Which location should I use?"
        assert history.messages[-1]["structured_payload"]["decision"] == decision.model_dump(mode="json")

    run_async_in_thread(_run())

###############################################################################
def test_general_question_uses_active_map_location_without_tool_call() -> None:
    async def _run() -> None:
        service, state, _ = _service()
        turn = _turn(user_text="What city is the map centered on?")
        response = await service.handle(
            request_id="request-context-location",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={"active_location": {"label": "Lugano"}},
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.tool_payload is None
        assert "Lugano" in response.assistant_message

    run_async_in_thread(_run())

###############################################################################
def test_context_question_bypasses_map_planning_and_parser_failure() -> None:
    async def _run() -> None:
        service, state, _ = _service()
        turn = _turn(
            user_text="Which city is the map centered on?",
            task_class="map_search",
            ambiguities=["parser_unavailable"],
        )
        response = await service.handle(
            request_id="request-context-map-search",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={
                "active_location": {"label": "Lugano"},
                "active_visualization": {
                    "resolved_location": {"label": "Lugano"},
                    "overlay_ids": [],
                },
            },
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.tool_payload is None
        assert "Lugano" in response.assistant_message
        assert response.operation is not None
        assert response.operation.kind == "direct_answer"

    run_async_in_thread(_run())

###############################################################################
def test_map_summary_bypasses_parser_failure_without_inventing_areas() -> None:
    async def _run() -> None:
        service, state, _ = _service()
        turn = _turn(
            user_text="Now summarize the three most interesting areas.",
            task_class="map_search",
            ambiguities=["parser_unavailable"],
        )
        response = await service.handle(
            request_id="request-context-summary",
            conversation_id="conversation",
            conversation_key="conversation",
            task=_task(state, turn),
            turn_contract=turn,
            latest_memory={
                "active_visualization": {
                    "resolved_location": {"label": "Athens, Greece"},
                    "basemap": {"label": "OpenStreetMap"},
                    "overlay_ids": [],
                }
            },
            latest_contract=None,
            recent_messages=[],
            context_usage=None,
        )

        assert response is not None
        assert response.tool_payload is None
        assert "Athens, Greece" in response.assistant_message
        assert response.operation is not None
        assert response.operation.kind == "direct_answer"

    run_async_in_thread(_run())
