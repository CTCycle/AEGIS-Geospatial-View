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
from server.repositories import agent_run_events as event_repo_module
from server.repositories import agent_runs as run_repo_module
from server.repositories import agent_steering as steering_repo_module
from server.repositories import conversations as conversation_repo_module
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
class _DatabaseHandle:

    # -------------------------------------------------------------------------
    def __init__(self, backend: object) -> None:
        self.backend = backend


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
    def __init__(self) -> None:
        self.started: list[str] = []

    # -------------------------------------------------------------------------
    async def execute_run(self, run_id: str) -> None:
        self.started.append(run_id)


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
    database = _DatabaseHandle(backend)
    monkeypatch.setattr(conversation_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(run_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(steering_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(event_repo_module, "get_database", lambda: database)

    publisher = RunEventPublisher(AgentRunEventRepository())
    run_repository = AgentRunRepository()
    aggregation = AggregatedRequestService()
    app = FastAPI()
    app.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    app.state.run_lifecycle_service = RunLifecycleService(
        conversation_repository=ConversationRepository(),
        run_repository=run_repository,
        aggregation_service=aggregation,
        event_publisher=publisher,
        run_orchestrator=_FakeRunOrchestrator(),  # type: ignore[arg-type]
    )
    app.state.run_steering_service = RunSteeringService(
        run_repository=run_repository,
        steering_repository=AgentSteeringRepository(),
        aggregation_service=aggregation,
        event_publisher=publisher,
    )
    app.state.run_event_stream_service = RunEventStreamService(
        publisher,
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
    assert first_event["payload"]["stage"] == "agent_started"

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
