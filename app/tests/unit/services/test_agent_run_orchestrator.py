from __future__ import annotations

from tests.conftest import run_async_in_thread
from datetime import UTC, datetime

from server.domain.agent.decision import PolicyDecision
from server.contracts.runs import AgentRunSnapshot, AgentRunState
from server.contracts.chat import ChatOperationResult, ChatTurnResponse
from server.contracts.events import RunEventType
from server.services.agent_runs.orchestrator import AgentRunOrchestrator

###############################################################################
class _FakeAgentOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(self, response: ChatTurnResponse) -> None:
        self.response = response

    # -------------------------------------------------------------------------
    async def run_turn(self, payload):  # noqa: ANN001
        _ = payload
        return self.response

###############################################################################
class _FakeRunRepository:

    # -------------------------------------------------------------------------
    def __init__(self, snapshot: AgentRunSnapshot) -> None:
        self.snapshot = snapshot
        self.completed = False
        self.failed: tuple[str, str] | None = None

    # -------------------------------------------------------------------------
    def get_run(self, run_id: str) -> AgentRunSnapshot | None:
        return self.snapshot if run_id == self.snapshot.run_id else None

    # -------------------------------------------------------------------------
    def mark_started(self, run_id: str) -> AgentRunSnapshot:
        assert run_id == self.snapshot.run_id
        self.snapshot = self.snapshot.model_copy(update={"state": AgentRunState.RUNNING})
        return self.snapshot

    # -------------------------------------------------------------------------
    def mark_started_if_current(
        self, run_id: str, expected_run_version: int
    ) -> tuple[AgentRunSnapshot, bool]:
        assert expected_run_version == self.snapshot.active_run_version
        return self.mark_started(run_id), True

    # -------------------------------------------------------------------------
    def mark_completed(self, run_id: str) -> AgentRunSnapshot:
        assert run_id == self.snapshot.run_id
        self.completed = True
        self.snapshot = self.snapshot.model_copy(update={"state": AgentRunState.COMPLETED})
        return self.snapshot

    # -------------------------------------------------------------------------
    def mark_completed_if_current(
        self, run_id: str, expected_run_version: int
    ) -> tuple[AgentRunSnapshot, bool]:
        assert expected_run_version == self.snapshot.active_run_version
        return self.mark_completed(run_id), True

    # -------------------------------------------------------------------------
    def mark_failed(self, run_id: str, code: str, message: str) -> AgentRunSnapshot:
        assert run_id == self.snapshot.run_id
        self.failed = (code, message)
        self.snapshot = self.snapshot.model_copy(
            update={
                "state": AgentRunState.FAILED,
                "error_code": code,
                "error_message": message,
            }
        )
        return self.snapshot

    # -------------------------------------------------------------------------
    def mark_failed_if_current(
        self, run_id: str, expected_run_version: int, code: str, message: str
    ) -> tuple[AgentRunSnapshot, bool]:
        assert expected_run_version == self.snapshot.active_run_version
        return self.mark_failed(run_id, code, message), True

    # -------------------------------------------------------------------------
    def request_cancel(self, run_id: str) -> AgentRunSnapshot:
        assert run_id == self.snapshot.run_id
        self.snapshot = self.snapshot.model_copy(update={"state": AgentRunState.CANCELLED})
        return self.snapshot

    # -------------------------------------------------------------------------
    def request_cancel_once(self, run_id: str) -> tuple[AgentRunSnapshot, bool]:
        return self.request_cancel(run_id), True

###############################################################################
class _FakeEventPublisher:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    # -------------------------------------------------------------------------
    async def publish(self, **kwargs):  # noqa: ANN003
        self.events.append(kwargs)

###############################################################################
def _snapshot() -> AgentRunSnapshot:
    return AgentRunSnapshot(
        conversation_id="conv_1",
        run_id="run_1",
        original_request="Map Rome",
        aggregated_request="Map Rome",
        active_run_version=1,
        state=AgentRunState.PENDING,
        created_at=datetime.now(UTC),
    )

###############################################################################
def _failed_response() -> ChatTurnResponse:
    return ChatTurnResponse(
        request_id="run_1",
        conversation_id="conv_1",
        assistant_message="Parser unavailable.",
        turn_contract={
            "task_class": "general_question",
            "user_text": "Map Rome",
            "conversation_context": {
                "recent_messages": [],
                "memory_snapshot": {},
            },
            "normalized_action": {
                "action_id": "ask",
                "action_label": "Ask",
                "requires_location": False,
                "task_tags": [],
                "action_tags": [],
            },
            "location_signals": [],
            "temporal_signal": {"mode": "none"},
            "ambiguities": ["parser_unavailable"],
            "disallowed_patterns": [],
            "parser_confidence": 0.0,
        },
        decision=PolicyDecision.model_validate(
            {
                "plan": {"state": "direct_response", "action_id": "ask", "mode": "direct_text"},
                "trace": {"steps": ["parser_failed"]},
            }
        ),
        operation=ChatOperationResult(
            kind="error",
            status="failed",
            message="Configured parser model is unavailable.",
        ),
    )

###############################################################################
def test_execute_run_marks_failed_operation_as_failed_run() -> None:
    repository = _FakeRunRepository(_snapshot())
    publisher = _FakeEventPublisher()
    orchestrator = AgentRunOrchestrator(
        agent_orchestrator=_FakeAgentOrchestrator(_failed_response()),  # type: ignore[arg-type]
        run_repository=repository,  # type: ignore[arg-type]
        event_publisher=publisher,  # type: ignore[arg-type]
        conversation_repository=object(),  # type: ignore[arg-type]
    )

    run_async_in_thread(orchestrator.execute_run("run_1"))

    assert repository.completed is False
    assert repository.failed == (
        "agent_operation_failed",
        "Configured parser model is unavailable.",
    )
    event_types = [event["type"] for event in publisher.events]
    assert RunEventType.ERROR in event_types
    assert RunEventType.COMPLETED not in event_types
