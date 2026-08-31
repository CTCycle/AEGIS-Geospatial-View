from __future__ import annotations

import pytest
import sqlalchemy
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.api.conversations import router as conversations_router
from server.common.paths import FASTAPI_API_PREFIX
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.chat_history import ChatHistoryRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.chat.conversation_snapshot import ConversationSnapshotService
from server.services.chat.history_service import ChatHistoryService


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
    assert snapshot_payload["task_snapshot"] is None
    assert snapshot_payload["map_session"] is None
    assert snapshot_payload["active_run"] is None


###############################################################################
def test_get_conversation_snapshot_returns_not_found_for_unknown_conversation(
    conversations_api_client: TestClient,
) -> None:
    response = conversations_api_client.get("/api/conversations/missing")

    assert response.status_code == 404
