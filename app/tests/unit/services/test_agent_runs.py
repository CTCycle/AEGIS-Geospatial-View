from __future__ import annotations

import asyncio

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.domain.agent_runs import AgentRunCreateRequest
from server.domain.run_events import RunEventCreate, RunEventType, RunEventVisibility
from server.domain.steering import SteeringMessageRequest
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
from server.services.agent_runs.exceptions import RunConflictError
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.steering import RunSteeringService

###############################################################################
class _DatabaseHandle:

    # -------------------------------------------------------------------------
    def __init__(self, backend) -> None:
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
@pytest.fixture()
def run_repositories(monkeypatch: pytest.MonkeyPatch):
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    database = _DatabaseHandle(backend)
    monkeypatch.setattr(conversation_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(run_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(steering_repo_module, "get_database", lambda: database)
    monkeypatch.setattr(event_repo_module, "get_database", lambda: database)
    return {
        "conversations": ConversationRepository(),
        "runs": AgentRunRepository(),
        "steering": AgentSteeringRepository(),
        "events": AgentRunEventRepository(),
    }

###############################################################################
def _services(run_repositories):
    publisher = RunEventPublisher(run_repositories["events"])
    aggregation = AggregatedRequestService()
    fake_orchestrator = _FakeRunOrchestrator()
    lifecycle = RunLifecycleService(
        conversation_repository=run_repositories["conversations"],
        run_repository=run_repositories["runs"],
        aggregation_service=aggregation,
        event_publisher=publisher,
        run_orchestrator=fake_orchestrator,  # type: ignore[arg-type]
    )
    steering = RunSteeringService(
        run_repository=run_repositories["runs"],
        steering_repository=run_repositories["steering"],
        aggregation_service=aggregation,
        event_publisher=publisher,
    )
    return lifecycle, steering, publisher, fake_orchestrator

###############################################################################
def test_aggregated_request_is_deterministic_and_preserves_order() -> None:
    service = AggregatedRequestService()
    aggregate = service.build_aggregated_request(
        "Map Rome", ["focus parks", "use satellite"]
    )

    assert aggregate == service.build_aggregated_request(
        "Map Rome", ["focus parks", "use satellite"]
    )
    assert "1. focus parks" in aggregate
    assert "2. use satellite" in aggregate

###############################################################################
def test_event_repository_replay_orders_and_filters_visibility(
    run_repositories,
) -> None:
    repo = run_repositories["events"]
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        from server.repositories.schemas.models import (
            AgentRunRecord,
            ConversationRecord,
        )

        session.add(ConversationRecord(id="conv_1", title="Events"))
        session.add(
            AgentRunRecord(
                id="run_1",
                conversation_id="conv_1",
                original_request="events",
                aggregated_request="events",
                active_slot=1,
            )
        )
        session.commit()
    visible = RunEventCreate(
        conversation_id="conv_1",
        run_id="run_1",
        run_version=1,
        type=RunEventType.PROGRESS,
        payload={"label": "one"},
    )
    first = repo.append_event(visible)
    repo.append_event(
        RunEventCreate(
            conversation_id="conv_1",
            run_id="run_1",
            run_version=1,
            type=RunEventType.ERROR,
            visibility=RunEventVisibility.INTERNAL,
            payload={"debug": "hidden"},
        )
    )
    second = repo.append_event(visible.model_copy(update={"payload": {"label": "two"}}))

    replay = repo.list_events("run_1", after_event_id=first.event_id)

    assert [event.event_id for event in replay] == [second.event_id]
    assert all(event.visibility == RunEventVisibility.USER for event in replay)

###############################################################################
def test_create_run_rejects_second_active_run(run_repositories) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")

    first = asyncio.run(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    with pytest.raises(RunConflictError):
        asyncio.run(
            lifecycle.create_run(
                conversation.conversation_id,
                AgentRunCreateRequest(message="Map Milan"),
            )
        )
    assert first.state == "pending"

###############################################################################
def test_conversation_context_state_survives_repository_restart(
    run_repositories,
) -> None:
    conversation = run_repositories["conversations"].create_conversation("Persistent")
    conversations = run_repositories["conversations"]
    initial = conversations.read_state(conversation.id)
    revision = conversations.write_state(
        conversation.id,
        expected_revision=initial["context_revision"],
        active_instructions=[{"directive_id": "dir_1", "status": "active"}],
        task_snapshot={"conversation_key": conversation.id, "tasks": []},
        memory_snapshot={"active_location": {"label": "Rome"}},
    )
    hydrated = conversations.read_state(conversation.id)
    assert hydrated["context_revision"] == revision
    assert hydrated["active_instructions"][0]["directive_id"] == "dir_1"
    assert hydrated["memory_snapshot"]["active_location"]["label"] == "Rome"
    with pytest.raises(ValueError, match="revision conflict"):
        conversations.write_state(
            conversation.id,
            expected_revision=initial["context_revision"],
            task_snapshot={"conversation_key": conversation.id, "tasks": []},
        )

###############################################################################
def test_steering_updates_same_run_and_is_idempotent(run_repositories) -> None:
    lifecycle, steering, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")
    run = asyncio.run(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    first = asyncio.run(
        steering.steer(
            conversation.conversation_id,
            run.run_id,
            SteeringMessageRequest(
                message="Focus on environmental layers.", client_mutation_id="m1"
            ),
        )
    )
    duplicate = asyncio.run(
        steering.steer(
            conversation.conversation_id,
            run.run_id,
            SteeringMessageRequest(
                message="Focus on environmental layers.", client_mutation_id="m1"
            ),
        )
    )

    assert first.run_id == run.run_id
    assert first.run_version == 2
    assert duplicate.steering_id == first.steering_id
    assert duplicate.run_version == 2

###############################################################################
def test_cancellation_is_terminal_and_blocks_later_steering(run_repositories) -> None:
    lifecycle, steering, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")
    run = asyncio.run(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    cancel = asyncio.run(lifecycle.cancel_run(conversation.conversation_id, run.run_id))

    assert cancel.state == "cancelled"
    with pytest.raises(RunConflictError):
        asyncio.run(
            steering.steer(
                conversation.conversation_id,
                run.run_id,
                SteeringMessageRequest(message="No, map Milan."),
            )
        )
