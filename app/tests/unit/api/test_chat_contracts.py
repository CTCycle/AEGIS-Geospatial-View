from __future__ import annotations

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
def test_chat_turn_contract_openapi_marks_conversation_id_required() -> None:
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

    assert response.turn_contract is None
    assert response.decision is None
    assert "turn_contract" not in response.model_dump(
        mode="json", exclude_none=True
    )


def test_chat_turn_preflights_conversation_before_orchestrator() -> None:
    orchestrator_called = False

    class _ConversationRepository:
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


def test_structured_probe_routes_return_latest_and_run_results() -> None:
    probe_result = StructuredProbeResponse(
        provider="opencode-go",
        model="deepseek-v4-flash",
        protocol="openai-compatible",
        status="passed",
        parse_status="complete",
        duration_ms=42,
        message="Structured parser probe passed.",
    )

    class _Probe:
        def latest(self) -> StructuredProbeResponse:
            return probe_result

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
