from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api.chat import get_chat_runtime, router
from server.common.paths import CHAT_TURN_ROUTE
from server.domain.chat import ChatTurnRequest


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
    assert any(error["loc"][-1] == "conversation_id" for error in response.json()["detail"])


###############################################################################
def test_chat_turn_contract_openapi_marks_conversation_id_required() -> None:
    schema = _app().openapi()
    request_schema = schema["components"]["schemas"]["ChatTurnRequest"]

    assert "conversation_id" in request_schema["required"]
    assert "/api/chat/turn" in schema["paths"]
    assert "/api/chat/jobs" in schema["paths"]
    assert "/api/chat/stream" in schema["paths"]


###############################################################################
def test_chat_turn_request_rejects_missing_conversation_id() -> None:
    try:
        ChatTurnRequest(message="Show Rome")
    except ValueError as exc:
        assert "conversation_id" in str(exc)
    else:
        raise AssertionError("conversation_id must be required")
