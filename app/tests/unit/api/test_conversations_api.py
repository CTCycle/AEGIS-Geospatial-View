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

    _message, revision = history.append_assistant_message_with_state(
        conversation_id=conversation.id,
        expected_revision=1,
        conversation_state={"marker": "committed"},
        content="First response",
        request_id="request-1",
    )

    assert revision == 2
    with pytest.raises(sqlalchemy.exc.IntegrityError):
        history.append_assistant_message_with_state(
            conversation_id=conversation.id,
            expected_revision=2,
            conversation_state={"marker": "must-roll-back"},
            content="Duplicate response",
            request_id="request-1",
        )

    persisted = conversations.get_conversation(conversation.id)
    assert persisted is not None
    assert persisted.context_revision == 2
    assert persisted.next_message_sequence == 1
    assert persisted.conversation_state == {"marker": "committed"}
    assert [
        item["content"]
        for item in history.list_messages(conversation_id=conversation.id)
    ] == ["First response"]


def test_native_provisional_assistant_is_upserted_on_resume() -> None:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    conversations = ConversationRepository(backend)
    history = ChatHistoryRepository(backend)
    conversation = conversations.create_conversation("Resumable map")

    first, revision = history.append_assistant_message_with_state(
        conversation_id=conversation.id,
        expected_revision=1,
        conversation_state={"marker": "pending"},
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
        conversation_state={"marker": "ready"},
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
