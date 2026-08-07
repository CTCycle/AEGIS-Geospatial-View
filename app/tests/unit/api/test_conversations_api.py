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
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import Base
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.lifecycle import RunLifecycleService

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
    publisher = RunEventPublisher(AgentRunEventRepository(backend))
    app = FastAPI()
    app.include_router(conversations_router, prefix=FASTAPI_API_PREFIX)
    app.state.run_lifecycle_service = RunLifecycleService(
        conversation_repository=ConversationRepository(backend),
        run_repository=run_repository,
        aggregation_service=AggregatedRequestService(),
        event_publisher=publisher,
        run_orchestrator=object(),  # type: ignore[arg-type]
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
