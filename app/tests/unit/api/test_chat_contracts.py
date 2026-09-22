from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.chat import get_chat_runtime, router
from server.common.paths import CHAT_STRUCTURED_PROBE_ROUTE, CHAT_TURN_ROUTE
from server.contracts.chat import (
    ChatOperationResult,
    ChatTurnRequest,
    ChatTurnResponse,
    StructuredProbeResponse,
)
from server.contracts.runs import AgentRunCreateResult, AgentRunSnapshot, AgentRunState
from server.services.agent_runs.exceptions import RunConflictError
from server.services.agent_runs.lifecycle import RunLifecycleService

###############################################################################
def _app() -> FastAPI:
    application = FastAPI()
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_chat_runtime] = lambda: object()
    return application

###############################################################################
def test_chat_turn_requires_conversation_id_over_http() -> None:
    response = TestClient(_app()).post(
        f"/api/chat{CHAT_TURN_ROUTE}",
        json={"message": "Show Rome"},
    )

    assert response.status_code == 422
    assert any(
        error["loc"][-1] == "conversation_id" for error in response.json()["detail"]
    )

###############################################################################
def test_chat_response_openapi_marks_conversation_id_required() -> None:
    schema = _app().openapi()
    request_schema = schema["components"]["schemas"]["ChatTurnRequest"]

    assert "conversation_id" in request_schema["required"]
    assert "/api/chat/turn" in schema["paths"]
    assert "/api/chat/jobs" in schema["paths"]
    assert "/api/chat/stream" in schema["paths"]

###############################################################################
def test_chat_settings_update_uses_patch_semantics() -> None:
    settings_path = _app().openapi()["paths"]["/api/chat/settings"]

    assert "patch" in settings_path
    assert "put" not in settings_path

###############################################################################
def test_chat_turn_request_rejects_missing_conversation_id() -> None:
    try:
        ChatTurnRequest(message="Show Rome")
    except ValueError as exc:
        assert "conversation_id" in str(exc)
    else:
        raise AssertionError("conversation_id must be required")

###############################################################################
def test_chat_turn_does_not_expose_map_commit_switch_over_http() -> None:
    response = TestClient(_app()).post(
        f"/api/chat{CHAT_TURN_ROUTE}",
        json={
            "message": "Show Rome",
            "conversation_id": "conv-1",
            "defer_map_commit": True,
        },
    )

    assert response.status_code == 422
    assert any(
        error["loc"][-1] == "defer_map_commit" for error in response.json()["detail"]
    )

###############################################################################
def test_native_turn_response_does_not_require_legacy_parser_projections() -> None:
    response = ChatTurnResponse(
        request_id="native-1",
        conversation_id="conv-1",
        assistant_message="Evidence is ready.",
        operation=ChatOperationResult(
            kind="direct_answer",
            status="success",
            message="Evidence is ready.",
        ),
    )

    assert response.route is None
    assert response.goal is None
    assert "turn_contract" not in response.model_dump(mode="json")

###############################################################################
def test_chat_turn_preflights_conversation_before_orchestrator() -> None:
    orchestrator_called = False

    ###############################################################################
    class _ConversationRepository:

        # -------------------------------------------------------------------------
        def get_conversation(self, conversation_id: str) -> None:  # noqa: ARG002
            return None

    async def _run_turn(_: object) -> None:
        nonlocal orchestrator_called
        orchestrator_called = True

    runtime = SimpleNamespace(
        conversation_repository=_ConversationRepository(),
        agent_orchestrator=SimpleNamespace(run_turn=_run_turn),
    )
    application = _app()
    application.dependency_overrides[get_chat_runtime] = lambda: runtime

    response = TestClient(application).post(
        f"/api/chat{CHAT_TURN_ROUTE}",
        json={"message": "Show Rome", "conversation_id": "missing"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."
    assert orchestrator_called is False

###############################################################################
class _ChatTurnLifecycleStub(RunLifecycleService):

    # -------------------------------------------------------------------------
    def __init__(
        self,
        *,
        response: ChatTurnResponse | None,
        result: AgentRunCreateResult,
        snapshot: AgentRunSnapshot | None = None,
        conflict: RunConflictError | None = None,
    ) -> None:
        self._response = response
        self._result = result
        self._snapshot = snapshot
        self._conflict = conflict
        self.run_repository = SimpleNamespace(
            get_run=lambda _run_id: self._snapshot
        )

    # -------------------------------------------------------------------------
    async def run_turn(self, *args, **kwargs):  # noqa: ANN002, ANN003
        if self._conflict is not None:
            raise self._conflict
        return self._response, self._result, True


def _chat_turn_runtime() -> SimpleNamespace:
    return SimpleNamespace(
        conversation_repository=SimpleNamespace(
            get_conversation=lambda _conversation_id: object()
        )
    )


def _chat_turn_result(state: AgentRunState) -> AgentRunCreateResult:
    return AgentRunCreateResult(
        conversation_id="conv-1",
        run_id="run-1",
        run_version=2,
        state=state,
    )


def _accepted_snapshot() -> AgentRunSnapshot:
    return AgentRunSnapshot(
        conversation_id="conv-1",
        run_id="run-1",
        original_request="Show Rome",
        aggregated_request="Show Rome",
        active_run_version=2,
        state=AgentRunState.PENDING,
        created_at=datetime.now(timezone.utc),
        presentation_status="pending",
    )


def _terminal_response() -> ChatTurnResponse:
    return ChatTurnResponse(
        request_id="request-1",
        conversation_id="conv-1",
        assistant_message="Evidence is ready.",
        operation=ChatOperationResult(
            kind="direct_answer",
            status="success",
            message="Evidence is ready.",
        ),
    )


def _post_with_lifecycle(lifecycle: _ChatTurnLifecycleStub):
    application = _app()
    application.state.run_lifecycle_service = lifecycle
    application.dependency_overrides[get_chat_runtime] = _chat_turn_runtime
    return TestClient(application).post(
        f"/api/chat{CHAT_TURN_ROUTE}",
        json={"message": "Show Rome", "conversation_id": "conv-1"},
    )


def test_chat_turn_returns_terminal_200_response() -> None:
    response = _post_with_lifecycle(
        _ChatTurnLifecycleStub(
            response=_terminal_response(),
            result=_chat_turn_result(AgentRunState.COMPLETED),
        )
    )

    assert response.status_code == 200
    assert response.json()["assistant_message"] == "Evidence is ready."


def test_chat_turn_returns_accepted_202_snapshot_contract() -> None:
    response = _post_with_lifecycle(
        _ChatTurnLifecycleStub(
            response=None,
            result=_chat_turn_result(AgentRunState.PENDING),
            snapshot=_accepted_snapshot(),
        )
    )

    assert response.status_code == 202
    assert response.json() == {
        "conversation_id": "conv-1",
        "run_id": "run-1",
        "run_version": 2,
        "state": "pending",
        "presentation_status": "pending",
        "status_url": "/api/conversations/conv-1/runs/run-1",
        "realtime_url": "/api/conversations/conv-1/realtime",
        "terminal": False,
    }


def test_chat_turn_returns_409_only_for_real_run_conflict() -> None:
    response = _post_with_lifecycle(
        _ChatTurnLifecycleStub(
            response=None,
            result=_chat_turn_result(AgentRunState.PENDING),
            conflict=RunConflictError("An active run already exists."),
        )
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "An active run already exists."

###############################################################################
def test_structured_probe_routes_return_latest_and_run_results() -> None:
    probe_result = StructuredProbeResponse(
        provider="opencode-go",
        model="deepseek-v4-flash",
        protocol="openai-compatible",
        status="passed",
        parse_status="complete",
        duration_ms=42,
        message="Native structured-response probe passed.",
    )

    ###############################################################################
    class _Probe:

        # -------------------------------------------------------------------------
        def latest(self) -> StructuredProbeResponse:
            return probe_result

        # -------------------------------------------------------------------------
        async def run(self) -> StructuredProbeResponse:
            return probe_result

    application = _app()
    application.dependency_overrides[get_chat_runtime] = lambda: SimpleNamespace(
        structured_probe_service=_Probe()
    )
    client = TestClient(application)

    latest = client.get(f"/api/chat{CHAT_STRUCTURED_PROBE_ROUTE}")
    executed = client.post(f"/api/chat{CHAT_STRUCTURED_PROBE_ROUTE}")

    assert latest.status_code == 200
    assert latest.json()["status"] == "passed"
    assert executed.status_code == 200
    assert executed.json()["parse_status"] == "complete"
