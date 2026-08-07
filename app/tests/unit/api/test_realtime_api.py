from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
import sqlalchemy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.conftest import run_async_in_thread
from server.api.realtime import metrics_router as realtime_metrics_router
from server.api.realtime import router as realtime_router
from server.api.conversations import router as conversations_router
from server.common.paths import FASTAPI_API_PREFIX
from server.domain.run_events import RunEventType
from server.domain.realtime import REALTIME_SUBPROTOCOL
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.metrics import RealtimeMetrics
from server.services.agent_runs.realtime import RealtimeConnectionRegistry
from server.services.agent_runs.steering import RunSteeringService


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
def realtime_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, FastAPI]]:
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
        if message.get("type") == "run.event" and message.get("payload", {}).get("type") == "completed":
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
def test_websocket_reconnect_replays_only_events_after_sequence(
    realtime_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = realtime_client
    conversation = client.post("/api/conversations", json={"title": "Replay"})
    conversation_id = conversation.json()["conversation_id"]
    path = f"/api/conversations/{conversation_id}/realtime"
    headers = {"origin": "http://127.0.0.1:8001"}
    with client.websocket_connect(path, subprotocols=[REALTIME_SUBPROTOCOL], headers=headers) as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json({
            "protocol_version": 1,
            "type": "run.start",
            "message_id": "replay-start",
            "payload": {"message": "Replay this", "client_request_id": "replay-1"},
        })
        first_event = None
        run_id = None
        while first_event is None:
            message = socket.receive_json()
            if message["type"] == "run.ack":
                run_id = message["payload"]["run_id"]
            if message["type"] == "run.event" and message["payload"]["type"] == "progress":
                first_event = message["payload"]
        assert first_event["sequence"] == 1
        assert run_id

    with client.websocket_connect(path, subprotocols=[REALTIME_SUBPROTOCOL], headers=headers) as socket:
        assert socket.receive_json()["type"] == "connection.ready"
        socket.send_json({
            "protocol_version": 1,
            "type": "session.resume",
            "message_id": "replay-resume",
            "payload": {"run_id": run_id, "after_sequence": 1},
        })
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
    first = client.post("/api/conversations", json={"title": "First"}).json()["conversation_id"]
    second = client.post("/api/conversations", json={"title": "Second"}).json()["conversation_id"]
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
