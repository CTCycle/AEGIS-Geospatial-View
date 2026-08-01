from __future__ import annotations

import json
import asyncio
from collections.abc import AsyncIterator

import pytest
import sqlalchemy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.api.conversations import router as conversations_router
from server.common.paths import FASTAPI_API_PREFIX
from server.domain.run_events import RunEventType
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.steering import RunSteeringService
from server.services.agent_runs.streaming import RunEventStreamService

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
class _FakeRunOrchestrator:

    # -------------------------------------------------------------------------
    def __init__(self, run_repository: AgentRunRepository, publisher: RunEventPublisher) -> None:
        self.started: list[str] = []
        self.run_repository = run_repository
        self.publisher = publisher

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> None:
        self.started.append(run_id)
        run = self.run_repository.get_run(run_id)
        await self.publisher.publish(
            conversation_id=run.conversation_id,
            run_id=run.run_id,
            run_version=run.active_run_version,
            type=RunEventType.PROGRESS,
            payload={
                "stage": "understanding_request",
                "label": "Understanding the request",
            },
        )

###############################################################################
async def _read_first_sse_event(stream: AsyncIterator[str]) -> dict:
    frame = await stream.__anext__()
    await stream.aclose()
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))

###############################################################################
@pytest.fixture()
def conversations_api_client(monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, FastAPI]:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)

    publisher = RunEventPublisher(AgentRunEventRepository(backend))
    run_repository = AgentRunRepository(backend)
    aggregation = AggregatedRequestService()
    app = FastAPI()
    app.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    app.state.run_lifecycle_service = RunLifecycleService(
        conversation_repository=ConversationRepository(backend),
        run_repository=run_repository,
        aggregation_service=aggregation,
        event_publisher=publisher,
        run_orchestrator=_FakeRunOrchestrator(run_repository, publisher),  # type: ignore[arg-type]
    )
    app.state.run_steering_service = RunSteeringService(
        run_repository=run_repository,
        steering_repository=AgentSteeringRepository(backend),
        aggregation_service=aggregation,
        event_publisher=publisher,
    )
    app.state.run_event_stream_service = RunEventStreamService(
        publisher,
        run_repository=run_repository,
        keep_alive_seconds=0.05,
    )

    client = TestClient(app)
    yield client, app
    client.close()

###############################################################################
def test_conversation_http_run_stream_and_steering_reach_same_agent_run(
    conversations_api_client: tuple[TestClient, FastAPI],
) -> None:
    client, app = conversations_api_client
    conversation_response = client.post(
        "/api/conversations",
        json={"title": "Rome map"},
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.json()["conversation_id"]

    run_response = client.post(
        f"/api/conversations/{conversation_id}/runs",
        json={"message": "Map Rome."},
    )
    assert run_response.status_code == 202
    run_payload = run_response.json()
    run_id = run_payload["run_id"]
    assert run_payload["stream_url"] == (
        f"/api/conversations/{conversation_id}/runs/{run_id}/events"
    )

    first_event = asyncio.run(
        _read_first_sse_event(
            app.state.run_event_stream_service.stream_sse(run_id, after_event_id=None),
        )
    )

    assert first_event["type"] == "progress"
    assert first_event["payload"]["stage"] == "understanding_request"

    steering_response = client.post(
        f"/api/conversations/{conversation_id}/runs/{run_id}/steering",
        json={
            "message": "Focus on public transport stops.",
            "client_mutation_id": "mutation-1",
        },
    )
    assert steering_response.status_code == 200
    steering_payload = steering_response.json()
    assert steering_payload["run_id"] == run_id
    assert steering_payload["run_version"] == 2
    assert "Map Rome." in steering_payload["aggregated_request"]
    assert "Focus on public transport stops." in steering_payload["aggregated_request"]

    update_event = asyncio.run(
        _read_first_sse_event(
            app.state.run_event_stream_service.stream_sse(
                run_id,
                after_event_id=first_event["event_id"],
            )
        )
    )

    assert update_event["type"] == "request_updated"
    assert update_event["run_id"] == run_id
    assert update_event["run_version"] == 2
    assert "public transport stops" in update_event["payload"]["aggregated_request"]

###############################################################################
def test_conversation_stream_rejects_run_from_different_conversation(
    conversations_api_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = conversations_api_client
    first = client.post("/api/conversations", json={"title": "First"})
    second = client.post("/api/conversations", json={"title": "Second"})
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["conversation_id"]
    second_id = second.json()["conversation_id"]

    run_response = client.post(
        f"/api/conversations/{first_id}/runs",
        json={"message": "Map Rome."},
    )
    assert run_response.status_code == 202
    run_id = run_response.json()["run_id"]

    stream_response = client.get(
        f"/api/conversations/{second_id}/runs/{run_id}/events"
    )

    assert stream_response.status_code == 404

###############################################################################
def test_run_creation_translates_conversation_access_denial_to_forbidden(
    conversations_api_client: tuple[TestClient, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, app = conversations_api_client
    conversation_response = client.post(
        "/api/conversations",
        json={"title": "Restricted conversation"},
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.json()["conversation_id"]

    def deny_access(
        _repository: ConversationRepository,
        _conversation_id: str,
        _owner_user_id: str | None = None,
    ) -> object:
        raise PermissionError("Conversation access denied.")

    monkeypatch.setattr(ConversationRepository, "verify_conversation_access", deny_access)

    response = client.post(
        f"/api/conversations/{conversation_id}/runs",
        json={"message": "Map Rome."},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Conversation access denied."

###############################################################################
def test_run_creation_translates_missing_conversation_to_not_found(
    conversations_api_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = conversations_api_client

    response = client.post(
        "/api/conversations/conv_missing/runs",
        json={"message": "Map Rome."},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found."

###############################################################################
def test_run_endpoints_translate_missing_run_to_not_found(
    conversations_api_client: tuple[TestClient, FastAPI],
) -> None:
    client, _app = conversations_api_client
    conversation_response = client.post(
        "/api/conversations",
        json={"title": "Missing run"},
    )
    assert conversation_response.status_code == 201
    conversation_id = conversation_response.json()["conversation_id"]
    missing_run_id = "run_missing"

    stream_response = client.get(
        f"/api/conversations/{conversation_id}/runs/{missing_run_id}/events"
    )
    steer_response = client.post(
        f"/api/conversations/{conversation_id}/runs/{missing_run_id}/steering",
        json={"message": "Focus on transport."},
    )
    cancel_response = client.post(
        f"/api/conversations/{conversation_id}/runs/{missing_run_id}/cancel"
    )

    assert stream_response.status_code == 404
    assert steer_response.status_code == 404
    assert cancel_response.status_code == 404

###############################################################################
def test_run_event_stream_requires_repository(
    conversations_api_client: tuple[TestClient, FastAPI],
) -> None:
    _client, app = conversations_api_client
    stream_service = app.state.run_event_stream_service

    with pytest.raises(TypeError):
        RunEventStreamService(stream_service.event_publisher)
