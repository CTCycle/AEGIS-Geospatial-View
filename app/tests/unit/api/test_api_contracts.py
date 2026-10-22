from __future__ import annotations
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
import sqlalchemy
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from server.api.chat import get_chat_runtime, router, get_models, pull_ollama_model
from server.common.paths import CHAT_TURN_ROUTE, FASTAPI_API_PREFIX
from server.contracts.chat import ChatOperationResult, ContextUsageResponse, ChatTurnRequest, ChatTurnResponse, OllamaPullRequest
from server.contracts.runs import AgentRunCreateResult, AgentRunSnapshot, AgentRunState
from server.services.agent_runs.exceptions import RunConflictError
from server.services.agent_runs.lifecycle import RunLifecycleService
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from server.api.conversations import router as conversations_router
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.chat.conversation_snapshot import ConversationSnapshotService
from server.services.chat.history_service import ChatHistoryService
from server.domain.agent.conversation import ConversationState
from collections.abc import Iterator
from starlette.websockets import WebSocketDisconnect
from tests.conftest import run_async_in_thread
from server.api.realtime import metrics_router as realtime_metrics_router, router as realtime_router
from server.contracts.events import RunEventType
from server.domain.realtime import REALTIME_SUBPROTOCOL, RealtimeServerMessage
from server.repositories.agent_steering import AgentSteeringRepository
from server.services.agent_runs.metrics import RealtimeMetrics
from server.services.agent_runs.realtime import RealtimeConnectionRegistry
from server.services.agent_runs.steering import RunSteeringService
from server.domain.agent.trace import public_protocol_projection

# --- test_chat_contracts.py ---




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
@pytest.mark.parametrize("route", [CHAT_TURN_ROUTE])
def test_chat_entry_points_reject_invalid_message_with_422_not_404(route: str) -> None:
    runtime = SimpleNamespace(
        conversation_repository=SimpleNamespace(
            get_conversation=lambda _conversation_id: object()
        )
    )
    application = _app()
    application.dependency_overrides[get_chat_runtime] = lambda: runtime
    # Validation happens before any run is created.

    response = TestClient(application).post(
        f"/api/chat{route}",
        json={"message": "x" * 12001, "conversation_id": "conv-1"},
    )

    assert response.status_code == 422
    assert "message is too long" in response.text
    assert "xxxx" not in response.text

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
        self.run_repository = SimpleNamespace(get_run=lambda _run_id: self._snapshot)

    # -------------------------------------------------------------------------
    async def run_turn(self, *args, **kwargs):  # noqa: ANN002, ANN003
        if self._conflict is not None:
            raise self._conflict
        return self._response, self._result, True


###############################################################################
def _chat_turn_runtime() -> SimpleNamespace:
    return SimpleNamespace(
        conversation_repository=SimpleNamespace(
            get_conversation=lambda _conversation_id: object()
        )
    )


###############################################################################
def _chat_turn_result(state: AgentRunState) -> AgentRunCreateResult:
    return AgentRunCreateResult(
        conversation_id="conv-1",
        run_id="run-1",
        run_version=2,
        state=state,
    )


###############################################################################
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


###############################################################################
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


###############################################################################
def _post_with_lifecycle(lifecycle: _ChatTurnLifecycleStub):
    application = _app()
    application.state.run_lifecycle_service = lifecycle
    application.dependency_overrides[get_chat_runtime] = _chat_turn_runtime
    return TestClient(application).post(
        f"/api/chat{CHAT_TURN_ROUTE}",
        json={"message": "Show Rome", "conversation_id": "conv-1"},
    )


###############################################################################
def test_chat_turn_returns_terminal_200_response() -> None:
    response = _post_with_lifecycle(
        _ChatTurnLifecycleStub(
            response=_terminal_response(),
            result=_chat_turn_result(AgentRunState.COMPLETED),
        )
    )

    assert response.status_code == 200
    assert response.json()["assistant_message"] == "Evidence is ready."


###############################################################################
def test_chat_turn_hydrates_completed_event_as_terminal_200() -> None:
    terminal = _terminal_response().model_copy(
        update={
            "context_usage": ContextUsageResponse(
                estimated_input_tokens=12,
                usage_percent=None,
                provider="opencode-go",
                model="deepseek-v4.1-flash",
            )
        }
    )
    event_payload = terminal.model_dump(mode="json", exclude_none=True)
    event_payload["content"] = terminal.assistant_message
    event_payload["state"] = AgentRunState.COMPLETED.value

    ###############################################################################
    class _PersistedTerminalLifecycleStub(_ChatTurnLifecycleStub):

        # -------------------------------------------------------------------------
        async def run_turn(self, *args, **kwargs):  # noqa: ANN002, ANN003
            response = self.read_completed_response("conv-1", "run-1")
            return response, self._result, True

    lifecycle = _PersistedTerminalLifecycleStub(
        response=None,
        result=_chat_turn_result(AgentRunState.COMPLETED),
        snapshot=_accepted_snapshot().model_copy(
            update={"state": AgentRunState.COMPLETED}
        ),
    )
    lifecycle.event_publisher = SimpleNamespace(
        replay=lambda _run_id: [
            SimpleNamespace(
                type=SimpleNamespace(value="completed"),
                payload=event_payload,
            )
        ]
    )

    response = _post_with_lifecycle(lifecycle)

    assert response.status_code == 200
    assert response.json()["assistant_message"] == "Evidence is ready."


###############################################################################
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


###############################################################################
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
def test_chat_turn_returns_503_for_unusable_provider() -> None:
    snapshot = _accepted_snapshot().model_copy(
        update={
            "state": AgentRunState.FAILED,
            "error_message": "The selected provider is unavailable.",
        }
    )
    response = _post_with_lifecycle(
        _ChatTurnLifecycleStub(
            response=None,
            result=_chat_turn_result(AgentRunState.FAILED),
            snapshot=snapshot,
        )
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "The selected provider is unavailable."

# --- test_chat_exception_safety.py ---




###############################################################################
class _FailingModelLibrary:

    # -------------------------------------------------------------------------
    def list_models(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        raise RuntimeError(
            "api-key=sk-test https://provider.invalid/v1 C:\\private\\models.json"
        )

###############################################################################
class _FailingMaintenance:

    # -------------------------------------------------------------------------
    def pull_ollama_model(self, payload):  # noqa: ANN001
        _ = payload
        raise RuntimeError(
            "api-key=sk-test https://ollama.invalid/api C:\\private\\ollama.log"
        )

###############################################################################
def test_model_catalog_exception_has_stable_public_message() -> None:
    runtime = SimpleNamespace(
        model_library_service=_FailingModelLibrary(),
        settings_service=SimpleNamespace(
            get_ollama_url=lambda: "http://ollama.invalid"
        ),
    )

    with pytest.raises(HTTPException) as raised:
        get_models(runtime=runtime)  # type: ignore[arg-type]

    assert raised.value.detail == "Could not load cloud models."
    assert "sk-test" not in str(raised.value.detail)
    assert "provider.invalid" not in str(raised.value.detail)
    assert "models.json" not in str(raised.value.detail)

###############################################################################
def test_ollama_pull_exception_has_stable_public_message() -> None:
    runtime = SimpleNamespace(maintenance_service=_FailingMaintenance())

    with pytest.raises(HTTPException) as raised:
        pull_ollama_model(
            OllamaPullRequest(model="test-model"),
            runtime=runtime,  # type: ignore[arg-type]
        )

    assert raised.value.detail == "Ollama pull failed."
    assert "sk-test" not in str(raised.value.detail)
    assert "ollama.invalid" not in str(raised.value.detail)
    assert "ollama.log" not in str(raised.value.detail)

# --- test_conversations_api.py ---



###############################################################################
class _InMemoryBackend:
    db_path = None

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.engine = sqlalchemy.create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.session = sessionmaker(bind=self.engine, future=True)

###############################################################################
@pytest.fixture()
def conversations_api_client() -> TestClient:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    run_repository = AgentRunRepository(backend)
    conversation_repository = ConversationRepository(backend)
    history_service = ChatHistoryService(ChatHistoryRepository(backend))
    publisher = RunEventPublisher(AgentRunEventRepository(backend))
    app = FastAPI()
    app.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    app.state.run_lifecycle_service = RunLifecycleService(
        conversation_repository=conversation_repository,
        run_repository=run_repository,
        aggregation_service=AggregatedRequestService(),
        event_publisher=publisher,
        run_orchestrator=object(),  # type: ignore[arg-type]
    )
    app.state.conversation_snapshot_service = ConversationSnapshotService(
        conversation_repository=conversation_repository,
        history_service=history_service,
        run_repository=run_repository,
    )
    client = TestClient(app)
    yield client
    client.close()

###############################################################################
def test_create_conversation_returns_persisted_conversation(
    conversations_api_client: TestClient,
) -> None:
    response = conversations_api_client.post(
        "/api/conversations",
        json={"title": "Rome map"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["conversation_id"]
    assert payload["title"] == "Rome map"

    snapshot = conversations_api_client.get(
        f"/api/conversations/{payload['conversation_id']}"
    )

    assert snapshot.status_code == 200
    snapshot_payload = snapshot.json()
    assert snapshot_payload["conversation_id"] == payload["conversation_id"]
    assert snapshot_payload["title"] == "Rome map"
    assert snapshot_payload["context_revision"] == 1
    assert snapshot_payload["messages"] == []
    assert (
        snapshot_payload["conversation_state"]["conversation_id"]
        == payload["conversation_id"]
    )
    assert snapshot_payload["memory_snapshot"] == {}
    assert snapshot_payload["map_session"] is None
    assert snapshot_payload["active_run"] is None

###############################################################################
def test_get_conversation_snapshot_returns_not_found_for_unknown_conversation(
    conversations_api_client: TestClient,
) -> None:
    response = conversations_api_client.get("/api/conversations/missing")

    assert response.status_code == 404

###############################################################################
def test_terminal_assistant_message_and_state_rollback_together() -> None:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    conversations = ConversationRepository(backend)
    history = ChatHistoryRepository(backend)
    conversation = conversations.create_conversation("Atomic persistence")

    committed_state = ConversationState.empty(conversation.id, revision=2).model_dump(
        mode="json"
    )
    _message, revision = history.append_assistant_message_with_state(
        conversation_id=conversation.id,
        expected_revision=1,
        conversation_state=committed_state,
        content="First response",
        request_id="request-1",
    )

    assert revision == 2
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        history.append_assistant_message_with_state(
            conversation_id=conversation.id,
            expected_revision=2,
            conversation_state=ConversationState.empty(
                conversation.id, revision=3
            ).model_dump(mode="json"),
            content="Duplicate response",
            request_id="request-1",
        )

    persisted = conversations.get_conversation(conversation.id)
    assert persisted is not None
    assert persisted.context_revision == 2
    assert persisted.next_message_sequence == 1
    assert persisted.conversation_state == committed_state
    assert [
        item["content"]
        for item in history.list_messages(conversation_id=conversation.id)
    ] == ["First response"]

###############################################################################
def test_native_provisional_assistant_is_upserted_on_resume() -> None:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    conversations = ConversationRepository(backend)
    history = ChatHistoryRepository(backend)
    conversation = conversations.create_conversation("Resumable map")

    first, revision = history.append_assistant_message_with_state(
        conversation_id=conversation.id,
        expected_revision=1,
        conversation_state=ConversationState.empty(
            conversation.id, revision=2
        ).model_dump(mode="json"),
        content="Data prepared; the map is loading.",
        request_id="run-1",
        structured_payload={
            "native": True,
            "presentation_status": "prepared",
        },
    )
    second, resumed_revision = history.append_assistant_message_with_state(
        conversation_id=conversation.id,
        expected_revision=revision,
        conversation_state=ConversationState.empty(
            conversation.id, revision=3
        ).model_dump(mode="json"),
        content="The map is ready.",
        request_id="run-1",
        structured_payload={
            "native": True,
            "presentation_status": "ready",
        },
    )

    assert resumed_revision == revision + 1
    assert second.id == first.id
    assert [
        item["content"]
        for item in history.list_messages(conversation_id=conversation.id)
    ] == ["The map is ready."]

# --- test_realtime_api.py ---





###############################################################################
def test_public_transports_omit_private_provider_continuation_without_mutation() -> None:
    private = {"execution_trace": {"checkpoint": {"execution_policy": {"max_iterations": 12},
        "provider_continuation": [{"google_content": {"parts": [{"thought_signature": "opaque"}]}}]}}}
    websocket = RealtimeServerMessage(type="run.completed", conversation_id="conversation", payload=private)
    output = websocket.model_dump(mode="json")
    assert "provider_continuation" not in output["payload"]["execution_trace"]["checkpoint"]
    assert "opaque" not in public_protocol_projection(private)
    assert "provider_continuation" in private["execution_trace"]["checkpoint"]
    assert output["payload"]["execution_trace"]["checkpoint"]["execution_policy"] == {"max_iterations": 12}

###############################################################################
class _Backend:
    db_path = None

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.engine = sqlalchemy.create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
        self.session = sessionmaker(bind=self.engine, future=True)

###############################################################################
class _Agent:

    # -------------------------------------------------------------------------
    def __init__(self, runs: AgentRunRepository, publisher: RunEventPublisher) -> None:
        self.runs = runs
        self.publisher = publisher

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> None:
        run = self.runs.get_run(run_id)
        assert run is not None
        await self.publisher.publish(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            type=RunEventType.PROGRESS,
            payload={"stage": "understanding_request", "label": "Understanding"},
        )
        await self.publisher.publish(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            type=RunEventType.ASSISTANT_TEXT_COMPLETED,
            payload={"content": f"Completed: {run.original_request}"},
        )
        await self.publisher.publish(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            type=RunEventType.COMPLETED,
            payload={"state": "completed"},
        )
        self.runs.mark_completed(run_id)

###############################################################################
@pytest.fixture()
def realtime_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, FastAPI]]:
    monkeypatch.setenv("FASTAPI_HOST", "127.0.0.1")
    monkeypatch.setenv("UI_HOST", "127.0.0.1")
    monkeypatch.setenv("UI_PORT", "8001")
    backend = _Backend()
    Base.metadata.create_all(backend.engine)
    conversations = ConversationRepository(backend)
    runs = AgentRunRepository(backend)
    publisher = RunEventPublisher(AgentRunEventRepository(backend))
    lifecycle = RunLifecycleService(
        conversation_repository=conversations,
        run_repository=runs,
        aggregation_service=AggregatedRequestService(),
        event_publisher=publisher,
        run_orchestrator=_Agent(runs, publisher),  # type: ignore[arg-type]
    )
    steering = RunSteeringService(
        run_repository=runs,
        steering_repository=AgentSteeringRepository(backend),
        aggregation_service=AggregatedRequestService(),
        event_publisher=publisher,
    )
    app = FastAPI()
    app.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    app.include_router(realtime_router, prefix=FASTAPI_API_PREFIX)
    app.include_router(realtime_metrics_router, prefix=FASTAPI_API_PREFIX)
    app.state.conversation_repository = conversations
    app.state.run_repository = runs
    app.state.run_lifecycle_service = lifecycle
    app.state.run_steering_service = steering
    app.state.run_event_publisher = publisher
    app.state.realtime_connections = RealtimeConnectionRegistry()
    app.state.realtime_metrics = RealtimeMetrics()
    client = TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    try:
        yield client, app
    finally:
        client.close()

###############################################################################
def _receive_until_terminal(socket) -> list[dict]:
    messages: list[dict] = []
    while True:
        message = socket.receive_json()
        messages.append(message)
        if (
            message.get("type") == "run.event"
            and message.get("payload", {}).get("type") == "completed"
        ):
            return messages

###############################################################################
def test_websocket_start_replays_ordered_events_and_deduplicates_retry(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    conversation = client.post("/api/conversations", json={"title": "Realtime"})
    assert conversation.status_code == 201
    conversation_id = conversation.json()["conversation_id"]
    with client.websocket_connect(
        f"/api/conversations/{conversation_id}/realtime",
        subprotocols=[REALTIME_SUBPROTOCOL],
        headers={"origin": "http://127.0.0.1:8001"},
    ) as socket:
        ready = socket.receive_json()
        assert ready["type"] == "connection.ready"
        socket.send_json(
            {
                "protocol_version": 1,
                "type": "session.resume",
                "message_id": "resume-1",
                "payload": {"run_id": None, "after_sequence": 0},
            }
        )
        assert socket.receive_json()["type"] == "session.resumed"
        socket.send_json(
            {
                "protocol_version": 1,
                "type": "run.start",
                "message_id": "start-1",
                "payload": {"message": "Map Rome", "client_request_id": "request-1"},
            }
        )
        messages = _receive_until_terminal(socket)
        acknowledgements = [item for item in messages if item["type"] == "run.ack"]
        events = [item["payload"] for item in messages if item["type"] == "run.event"]
        assert acknowledgements[0]["payload"]["duplicate"] is False
        assert [item["sequence"] for item in events] == [1, 2, 3]
        assert [item["type"] for item in events] == [
            "progress",
            "assistant_text_completed",
            "completed",
        ]
        socket.send_json(
            {
                "protocol_version": 1,
                "type": "run.start",
                "message_id": "start-duplicate",
                "payload": {"message": "Map Rome", "client_request_id": "request-1"},
            }
        )
        duplicate_ack = socket.receive_json()
        assert duplicate_ack["type"] == "run.ack"
        assert duplicate_ack["payload"]["duplicate"] is True

###############################################################################
def test_websocket_route_rejects_wrong_origin(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    conversation = client.post("/api/conversations", json={"title": "Origin"})
    conversation_id = conversation.json()["conversation_id"]
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/api/conversations/{conversation_id}/realtime",
            subprotocols=[REALTIME_SUBPROTOCOL],
            headers={"origin": "http://evil.example"},
        ):
            pass

###############################################################################
def test_websocket_route_accepts_backend_served_origin(
    realtime_client: tuple[TestClient, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FASTAPI_PORT", "5002")
    client, _app = realtime_client
    conversation = client.post("/api/conversations", json={"title": "Same origin"})
    conversation_id = conversation.json()["conversation_id"]
    with client.websocket_connect(
        f"/api/conversations/{conversation_id}/realtime",
        subprotocols=[REALTIME_SUBPROTOCOL],
        headers={"origin": "http://127.0.0.1:5002"},
    ) as socket:
        assert socket.receive_json()["type"] == "connection.ready"

###############################################################################
def test_websocket_reconnect_replays_only_events_after_sequence(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    conversation = client.post("/api/conversations", json={"title": "Replay"})
    conversation_id = conversation.json()["conversation_id"]
    path = f"/api/conversations/{conversation_id}/realtime"
    headers = {"origin": "http://127.0.0.1:8001"}
    with client.websocket_connect(
        path, subprotocols=[REALTIME_SUBPROTOCOL], headers=headers
    ) as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json(
            {
                "protocol_version": 1,
                "type": "run.start",
                "message_id": "replay-start",
                "payload": {"message": "Replay this", "client_request_id": "replay-1"},
            }
        )
        first_event = None
        run_id = None
        while first_event is None:
            message = socket.receive_json()
            if message["type"] == "run.ack":
                run_id = message["payload"]["run_id"]
            if (
                message["type"] == "run.event"
                and message["payload"]["type"] == "progress"
            ):
                first_event = message["payload"]
        assert first_event["sequence"] == 1
        assert run_id

    with client.websocket_connect(
        path, subprotocols=[REALTIME_SUBPROTOCOL], headers=headers
    ) as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json(
            {
                "protocol_version": 1,
                "type": "session.resume",
                "message_id": "replay-resume",
                "payload": {"run_id": run_id, "after_sequence": 1},
            }
        )
        messages = [socket.receive_json()]
        while not any(
            item["type"] == "run.event" and item["payload"]["type"] == "completed"
            for item in messages
        ):
            messages.append(socket.receive_json())
        replayed = [item["payload"] for item in messages if item["type"] == "run.event"]
        assert [item["sequence"] for item in replayed] == [2, 3]
        assert all(item["conversation_id"] == conversation_id for item in replayed)

###############################################################################
async def _assert_concurrent_conversations_keep_event_routing_isolated(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    first = client.post("/api/conversations", json={"title": "First"}).json()[
        "conversation_id"
    ]
    second = client.post("/api/conversations", json={"title": "Second"}).json()[
        "conversation_id"
    ]
    runs = _app.state.run_repository
    publisher = _app.state.run_event_publisher
    first_run = runs.create_run(first, "first", "first")
    second_run = runs.create_run(second, "second", "second")

    async def collect(run_id: str) -> list[tuple[str, int]]:
        result: list[tuple[str, int]] = []
        async for event in publisher.events(run_id):
            result.append((event.conversation_id, event.sequence))
            if len(result) == 3:
                return result
        return result

    async def publish(run_id: str, conversation_id: str) -> None:
        for index in range(3):
            await publisher.publish(
                conversation_id=conversation_id,
                run_id=run_id,
                run_version=1,
                type=RunEventType.PROGRESS,
                payload={"stage": f"step-{index}"},
            )

    results = await asyncio.gather(
        collect(first_run.run_id),
        collect(second_run.run_id),
        publish(first_run.run_id, first),
        publish(second_run.run_id, second),
    )
    first_events, second_events = results[:2]
    assert first_events == [(first, 1), (first, 2), (first, 3)]
    assert second_events == [(second, 1), (second, 2), (second, 3)]

###############################################################################
def test_concurrent_conversations_keep_event_routing_isolated(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    run_async_in_thread(
        _assert_concurrent_conversations_keep_event_routing_isolated(realtime_client)
    )

###############################################################################
def test_realtime_metrics_are_loopback_only(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    response = client.get("/api/realtime/metrics")
    assert response.status_code == 200
    assert response.json()["active_connections"] == 0