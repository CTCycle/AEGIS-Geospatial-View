from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from tests.conftest import run_async_in_thread

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from server.contracts.runs import AgentRunCreateRequest, AgentRunState
from server.contracts.events import RunEventCreate, RunEventType, RunEventVisibility
from server.domain.agent.capability_route import AgentPhase, AgentRunState as NativeRunState
from server.domain.agent.trace import AgentCheckpoint, AgentTraceEvent
from server.domain.steering import SteeringMessageRequest
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.agent_steering import AgentSteeringRepository
from server.repositories.conversations import ConversationRepository
from server.repositories.schemas.models import (
    AgentRunRecord,
    Base,
    ChatMessageRecord,
    ConversationRecord,
)
from server.domain.agent.conversation import ConversationState
from server.services.agent_runs.aggregation import AggregatedRequestService
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.exceptions import RunConflictError
from server.services.agent_runs.lifecycle import RunLifecycleService
from server.services.agent_runs.steering import RunSteeringService

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
def run_repositories() -> dict[str, object]:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    event_repository = AgentRunEventRepository(backend)
    return {
        "conversations": ConversationRepository(backend),
        "runs": AgentRunRepository(backend, event_repository=event_repository),
        "steering": AgentSteeringRepository(backend),
        "events": event_repository,
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

    replay = repo.list_events("run_1", after_sequence=first.sequence)

    assert [event.event_id for event in replay] == [second.event_id]
    assert all(event.visibility == RunEventVisibility.USER for event in replay)


###############################################################################
def test_event_repository_loads_latest_native_checkpoint_for_run_version(
    run_repositories,
) -> None:
    repo = run_repositories["events"]
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        session.add(ConversationRecord(id="conv_checkpoint", title="Checkpoints"))
        session.add(
            AgentRunRecord(
                id="run_checkpoint",
                conversation_id="conv_checkpoint",
                original_request="find hospitals",
                aggregated_request="find hospitals",
                active_slot=1,
            )
        )
        session.commit()

    state = NativeRunState(
        request_id="request_checkpoint",
        conversation_id="conv_checkpoint",
        phase=AgentPhase.MODEL_STEP,
        user_message="find hospitals",
    ).checkpoint()
    first = AgentCheckpoint(
        run_id="run_checkpoint",
        conversation_id="conv_checkpoint",
        run_version=1,
        conversation_state={},
        run_state=state,
        state_hash="first",
    )
    second_state = dict(state)
    second_state["request_id"] = "request_checkpoint_2"
    second = first.model_copy(
        update={"run_state": second_state, "state_hash": "second"}
    )
    repo.append_event(
        RunEventCreate(
            conversation_id="conv_checkpoint",
            run_id="run_checkpoint",
            run_version=1,
            type=RunEventType.CHECKPOINT,
            visibility=RunEventVisibility.INTERNAL,
            payload=AgentTraceEvent(
                kind="checkpoint",
                run_id="run_checkpoint",
                run_version=1,
                sequence=1,
                payload=first.model_dump(mode="json"),
            ).model_dump(mode="json"),
        )
    )
    repo.append_event(
        RunEventCreate(
            conversation_id="conv_checkpoint",
            run_id="run_checkpoint",
            run_version=1,
            type=RunEventType.CHECKPOINT,
            visibility=RunEventVisibility.INTERNAL,
            payload=AgentTraceEvent(
                kind="checkpoint",
                run_id="run_checkpoint",
                run_version=1,
                sequence=2,
                payload=second.model_dump(mode="json"),
            ).model_dump(mode="json"),
        )
    )

    loaded = repo.get_latest_checkpoint_state(
        "run_checkpoint", run_version=1
    )

    assert loaded is not None
    assert loaded["request_id"] == "request_checkpoint_2"
    assert (
        repo.get_latest_checkpoint_state("run_checkpoint", run_version=2)
        is None
    )

###############################################################################
def test_event_repository_rejects_run_and_conversation_mismatch(
    run_repositories,
) -> None:
    repo = run_repositories["events"]
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        session.add(ConversationRecord(id="conv_1", title="Events"))
        session.add(ConversationRecord(id="conv_2", title="Other events"))
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

    with pytest.raises(ValueError, match="Run not found"):
        repo.append_event(
            RunEventCreate(
                conversation_id="conv_2",
                run_id="run_1",
                run_version=1,
                type=RunEventType.PROGRESS,
            )
        )

    assert repo.get_last_sequence("run_1") == 0

###############################################################################
def test_create_run_rejects_second_active_run(run_repositories) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")

    first = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    with pytest.raises(RunConflictError):
        run_async_in_thread(
            lifecycle.create_run(
                conversation.conversation_id,
                AgentRunCreateRequest(message="Map Milan"),
            )
        )
    assert first.state == "pending"


###############################################################################
def test_terminal_render_failure_and_cancellation_close_pending_presentation(
    run_repositories,
) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Render terminal state")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )
    repository = run_repositories["runs"]
    with repository._session_factory() as session:  # noqa: SLF001
        record = session.get(AgentRunRecord, run.run_id)
        assert record is not None
        record.presentation_status = "pending"
        record.presentation_json = {
            "status": "pending",
            "pending_response": {"assistant_message": "Map is loading."},
        }
        session.commit()

    failed, transitioned = repository.mark_failed_if_current(
        run.run_id,
        run.run_version,
        "render_failed",
        "The browser rejected the map layer.",
    )
    assert transitioned is True
    assert failed.state == AgentRunState.FAILED
    assert failed.presentation_status == "failed"
    assert failed.presentation is not None
    assert failed.presentation["status"] == "failed"
    assert "pending_response" not in failed.presentation

    cancelled_run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Milan"),
        )
    )
    with repository._session_factory() as session:  # noqa: SLF001
        record = session.get(AgentRunRecord, cancelled_run.run_id)
        assert record is not None
        record.presentation_status = "pending"
        record.presentation_json = {
            "status": "pending",
            "pending_response": {"assistant_message": "Map is loading."},
        }
        session.commit()

    cancelled, transitioned = repository.request_cancel_once(cancelled_run.run_id)
    assert transitioned is True
    assert cancelled.state == AgentRunState.CANCELLED
    assert cancelled.presentation_status == "failed"
    assert cancelled.presentation is not None
    assert cancelled.presentation["status"] == "failed"
    assert "pending_response" not in cancelled.presentation


###############################################################################
def test_explicit_pending_failure_status_is_normalized_atomically(run_repositories) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Explicit pending failure")
    run_result, _ = run_async_in_thread(
        lifecycle.create_run_with_status(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
            schedule=False,
        )
    )
    repository = run_repositories["runs"]
    with repository._session_factory() as session:  # noqa: SLF001
        record = session.get(AgentRunRecord, run_result.run_id)
        assert record is not None
        record.presentation_status = "pending"
        session.commit()

    failed, transitioned = repository.mark_failed_if_current(
        run_result.run_id,
        run_result.run_version,
        "render_failed",
        "The browser rejected the map layer.",
        presentation_status="pending",
    )

    assert transitioned is True
    assert failed.state == AgentRunState.FAILED
    assert failed.presentation_status == "failed"


###############################################################################
def test_superseding_pending_render_closes_the_old_presentation(
    run_repositories,
) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Superseded presentation")
    old_result, _ = run_async_in_thread(
        lifecycle.create_run_with_status(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
            schedule=False,
        )
    )
    repository = run_repositories["runs"]
    repository.prepare_render(
        old_result.run_id,
        old_result.run_version,
        {
            "status": "pending",
            "map_session_id": "map-old",
            "collection_revision": 1,
            "pending_response": {"map_session": {"session_id": "map-old"}},
            "required_render_checks": {},
            "completion_requirements": [],
        },
    )

    new_result, created = run_async_in_thread(
        lifecycle.create_run_with_status(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Milan"),
            schedule=False,
        )
    )

    assert created is True
    assert new_result.run_id != old_result.run_id
    superseded = repository.get_run(old_result.run_id)
    assert superseded is not None
    assert superseded.state == AgentRunState.CANCELLED
    assert superseded.error_code == "superseded"
    assert superseded.presentation_status == "not_required"
    assert superseded.presentation is None


###############################################################################
@pytest.mark.asyncio
async def test_lifecycle_resumes_persisted_active_native_run(run_repositories) -> None:
    lifecycle, _, _, fake_orchestrator = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Resume")
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        session.add(
            AgentRunRecord(
                id="run_restart",
                conversation_id=conversation.conversation_id,
                original_request="Find hospitals",
                aggregated_request="Find hospitals",
                state=AgentRunState.RUNNING.value,
                active_slot=1,
            )
        )
        session.commit()

    assert lifecycle.resume_active_runs() == 1
    await asyncio.sleep(0)
    await lifecycle.shutdown()

    assert fake_orchestrator.started == ["run_restart"]

###############################################################################
def test_duplicate_run_start_is_idempotent_while_active(run_repositories) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Idempotency")

    first, created = run_async_in_thread(
        lifecycle.create_run_with_status(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome", client_request_id="request-1"),
        )
    )
    duplicate, duplicate_created = run_async_in_thread(
        lifecycle.create_run_with_status(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Milan", client_request_id="request-1"),
        )
    )

    assert created is True
    assert duplicate_created is False
    assert duplicate.run_id == first.run_id
    assert duplicate.state == first.state

###############################################################################
def test_conversation_context_state_survives_repository_restart(
    run_repositories,
) -> None:
    conversation = run_repositories["conversations"].create_conversation("Persistent")
    conversations = run_repositories["conversations"]
    initial = conversations.read_state(conversation.id)
    state = ConversationState(
        conversation_id=conversation.id,
        active_directives=[{"directive_id": "dir_1", "status": "active"}],
        constraints={"source": "test"},
        resolved_locations={
            "active_location": {
                "label": "Rome",
                "latitude": 41.9,
                "longitude": 12.5,
            }
        },
    )
    revision = conversations.write_state(
        conversation.id,
        expected_revision=initial["context_revision"],
        conversation_state=state.model_dump(mode="json"),
    )
    hydrated = conversations.read_state(conversation.id)
    assert hydrated["context_revision"] == revision
    assert hydrated["conversation_state"]["active_directives"][0]["directive_id"] == "dir_1"
    hydrated_state = ConversationState.model_validate(hydrated["conversation_state"])
    assert hydrated_state.memory_projection()["active_location"]["label"] == "Rome"
    with pytest.raises(ValueError, match="revision conflict"):
        conversations.write_state(
            conversation.id,
            expected_revision=initial["context_revision"],
            conversation_state=state.model_dump(mode="json"),
        )


###############################################################################
def test_conversation_repository_canonicalizes_legacy_state_on_write(
    run_repositories,
) -> None:
    conversations = run_repositories["conversations"]
    conversation = conversations.create_conversation("Legacy state")

    revision = conversations.write_state(
        conversation.id,
        expected_revision=1,
        conversation_state={
            "schema_version": 1,
            "conversation_id": conversation.id,
            "revision": 1,
            "unresolved_questions": ["Which country contains Lake Bracciano?"],
        },
    )

    persisted = conversations.read_state(conversation.id)
    assert revision == 2
    assert persisted["conversation_state"]["schema_version"] == 2
    assert persisted["conversation_state"]["revision"] == 2
    assert "unresolved_questions" not in persisted["conversation_state"]
    assert (
        persisted["conversation_state"]["pending_clarification"]["question"]
        == "Which country contains Lake Bracciano?"
    )

###############################################################################
def test_steering_updates_same_run_and_is_idempotent(run_repositories) -> None:
    lifecycle, steering, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    first = run_async_in_thread(
        steering.steer(
            conversation.conversation_id,
            run.run_id,
            SteeringMessageRequest(
                message="Focus on environmental layers.", client_mutation_id="m1"
            ),
        )
    )
    duplicate = run_async_in_thread(
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
    assert first.duplicate is False
    assert duplicate.steering_id == first.steering_id
    assert duplicate.run_version == 2
    assert duplicate.duplicate is True

###############################################################################
def test_safe_steering_persists_a_v2_state_delta(run_repositories) -> None:
    lifecycle, _, publisher, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Zurich")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Find Zurich and show weather."),
        )
    )
    conversations = run_repositories["conversations"]
    initial = conversations.read_state(conversation.conversation_id)
    state = ConversationState(
        conversation_id=conversation.conversation_id,
        evidence_refs=["weather-layer"],
        constraints={"geographic_scope": {"radius_m": 10_000}},
    )
    conversations.write_state(
        conversation.conversation_id,
        expected_revision=initial["context_revision"],
        conversation_state=state.model_dump(mode="json"),
    )
    steering = RunSteeringService(
        run_repository=run_repositories["runs"],
        steering_repository=run_repositories["steering"],
        aggregation_service=AggregatedRequestService(),
        event_publisher=publisher,
        conversation_repository=conversations,
    )

    response = run_async_in_thread(
        steering.steer(
            conversation.conversation_id,
            run.run_id,
            SteeringMessageRequest(message="Expand the area to 50 km."),
        )
    )

    persisted = conversations.read_state(conversation.conversation_id)
    snapshot = persisted["conversation_state"]
    assert response.state_delta_applied is True
    assert snapshot["constraints"]["latest_steering"]["kind"] == "scope_change"
    assert snapshot["constraints"]["latest_steering"]["parameters"]["radius_text"] == "50 km"
    assert snapshot["evidence_refs"] == ["weather-layer"]
    assert (
        run_repositories["steering"]
        .list_steering_messages(run.run_id)[0]
        .state_delta_applied
        is True
    )

###############################################################################
def test_cancellation_is_terminal_and_blocks_later_steering(run_repositories) -> None:
    lifecycle, steering, publisher, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Rome")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Map Rome"),
        )
    )

    cancel = run_async_in_thread(
        lifecycle.cancel_run(conversation.conversation_id, run.run_id)
    )
    duplicate_cancel = run_async_in_thread(
        lifecycle.cancel_run(conversation.conversation_id, run.run_id)
    )

    assert cancel.state == "cancelled"
    assert duplicate_cancel.state == "cancelled"
    assert len(publisher.replay(run.run_id)) == 1
    cancelled_snapshot, transitioned = run_repositories[
        "runs"
    ].mark_completed_if_current(run.run_id, run.run_version)
    assert transitioned is False
    assert cancelled_snapshot.state == "cancelled"
    with pytest.raises(RunConflictError):
        run_async_in_thread(
            steering.steer(
                conversation.conversation_id,
                run.run_id,
                SteeringMessageRequest(message="No, map Milan."),
            )
        )

###############################################################################
def test_shutdown_cancels_in_flight_tasks_and_clears_task_registry(
    run_repositories,
) -> None:
    async def _run() -> None:
        lifecycle, _, _, _ = _services(run_repositories)
        started = asyncio.Event()
        release = asyncio.Event()

        async def long_running() -> None:
            started.set()
            await release.wait()

        long_task = asyncio.create_task(long_running())
        completed_task = asyncio.create_task(asyncio.sleep(0))
        lifecycle._tasks.update({long_task, completed_task})  # noqa: SLF001
        await started.wait()
        await completed_task

        await lifecycle.shutdown()

        assert long_task.cancelled()
        assert not lifecycle._tasks  # noqa: SLF001

    run_async_in_thread(_run())

###############################################################################
def test_cancel_run_cancels_the_matching_in_flight_task(run_repositories) -> None:

    ###############################################################################
    class _BlockingOrchestrator:

        # -------------------------------------------------------------------------
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False
            self.release = asyncio.Event()

        # -------------------------------------------------------------------------
        async def execute_run(self, _run_id: str) -> None:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    async def _run() -> None:
        publisher = RunEventPublisher(run_repositories["events"])
        orchestrator = _BlockingOrchestrator()
        lifecycle = RunLifecycleService(
            conversation_repository=run_repositories["conversations"],
            run_repository=run_repositories["runs"],
            aggregation_service=AggregatedRequestService(),
            event_publisher=publisher,
            run_orchestrator=orchestrator,  # type: ignore[arg-type]
        )
        conversation = lifecycle.create_conversation(title="Cancel in flight")
        run = await lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Wait for provider"),
        )
        await orchestrator.started.wait()

        response = await lifecycle.cancel_run(
            conversation.conversation_id,
            run.run_id,
        )
        await asyncio.sleep(0)

        assert response.state == "cancelled"
        assert orchestrator.cancelled is True
        await lifecycle.shutdown()

    run_async_in_thread(_run())

###############################################################################
def test_render_acknowledgment_promotes_candidate_once_and_is_idempotent(
    run_repositories,
) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Render handshake")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Show earthquakes in Rome"),
        )
    )
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        session.add(
            ChatMessageRecord(
                conversation_id=conversation.conversation_id,
                turn_index=1,
                request_id=run.run_id,
                role="assistant",
                content="Data prepared; the map is loading.",
            )
        )
        session.commit()
    candidate_map = {
        "session_id": "map-session-1",
        "resolved_location": {
            "label": "Rome, Italy",
            "latitude": 41.9028,
            "longitude": 12.4964,
            "location_type": "city",
            "bbox": [12.3, 41.7, 12.7, 42.1],
        },
        "basemap_id": "osm_standard",
        "viewport": {
            "center_latitude": 41.9028,
            "center_longitude": 12.4964,
            "radius_m": 25_000,
            "bbox": [12.3, 41.7, 12.7, 42.1],
        },
        "bounds": [12.3, 41.7, 12.7, 42.1],
        "payload": {"result_status": "valid_empty"},
        "overlay_collection": {
            "collection_id": "active-map",
            "revision": 4,
            "instances": [],
        },
    }
    presentation = {
        "status": "pending",
        "map_session_id": "map-session-1",
        "collection_revision": 4,
        "pending_response": {
            "assistant_message": "Data prepared; the map is loading.",
            "map_session": candidate_map,
            "task_state": {
                "root_task_id": "task-root-render-handshake",
                "active_task_id": "task-root-render-handshake",
                "status": "in_progress",
                "current_iteration": 1,
                "max_iterations": 12,
                "tasks": [
                    {
                        "task_id": "task-root-render-handshake",
                        "description": "Show earthquakes in Rome",
                        "status": "in_progress",
                    }
                ],
                "completion_requirements": [
                    {
                        "name": "map_candidate_prepared",
                        "required": True,
                        "status": "satisfied",
                    }
                ],
            },
            "memory_snapshot": {"active_location": {"label": "Rome"}},
            "conversation_state": {
                "conversation_id": conversation.conversation_id,
                "revision": 0,
            },
        },
        "required_render_checks": {
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
        "completion_requirements": [
            {
                "name": "map_candidate_prepared",
                "required": True,
                "status": "satisfied",
            }
        ],
    }
    prepared, transitioned = run_repositories["runs"].prepare_render(
        run.run_id,
        run.run_version,
        presentation,
    )
    assert transitioned is True
    assert prepared.state.value == "awaiting_render"

    acknowledgment = {
        "run_id": run.run_id,
        "run_version": run.run_version,
        "map_session_id": "map-session-1",
        "collection_revision": 4,
        "status": "ready",
        "viewport_bounds": [12.3, 41.7, 12.7, 42.1],
        "checks": {
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
        "overlay_results": [],
        "failure_code": None,
    }
    completed, duplicate, completed_response = (
        run_repositories["runs"].acknowledge_render(
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            run_version=run.run_version,
            map_session_id="map-session-1",
            collection_revision=4,
            status="ready",
            acknowledgment=acknowledgment,
        )
    )
    assert completed.state.value == "completed"
    assert completed.presentation_status == "ready"
    assert duplicate is False
    assert completed_response["task_state"]["status"] == "completed"
    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        message = session.scalar(
            sqlalchemy.select(ChatMessageRecord).where(
                ChatMessageRecord.conversation_id == conversation.conversation_id,
                ChatMessageRecord.request_id == run.run_id,
            )
        )
        assert message is not None
        assert message.content == (
            "The map is ready. No results were found in the requested area or time window."
        )
        assert message.map_session == candidate_map
    revision_after_commit = run_repositories["conversations"].read_state(
        conversation.conversation_id
    )["context_revision"]

    replay, duplicate, _ = run_repositories["runs"].acknowledge_render(
        conversation_id=conversation.conversation_id,
        run_id=run.run_id,
        run_version=run.run_version,
        map_session_id="map-session-1",
        collection_revision=4,
        status="ready",
        acknowledgment=acknowledgment,
    )
    assert replay.state.value == "completed"
    assert duplicate is True
    assert run_repositories["conversations"].read_state(
        conversation.conversation_id
    )["context_revision"] == revision_after_commit

###############################################################################
def test_stale_render_ack_cannot_mutate_pending_candidate(run_repositories) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Stale render")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Show Rome"),
        )
    )
    run_repositories["runs"].prepare_render(
        run.run_id,
        run.run_version,
        {
            "status": "pending",
            "map_session_id": "map-session-2",
            "collection_revision": 7,
            "pending_response": {"map_session": {"session_id": "map-session-2"}},
            "required_render_checks": {},
            "completion_requirements": [],
        },
    )

    with pytest.raises(ValueError, match="does not match"):
        run_repositories["runs"].acknowledge_render(
            conversation_id=conversation.conversation_id,
            run_id=run.run_id,
            run_version=run.run_version,
            map_session_id="map-session-2",
            collection_revision=8,
            status="ready",
            acknowledgment={"status": "ready"},
        )
    assert run_repositories["runs"].get_run(run.run_id).state.value == "awaiting_render"

###############################################################################
def test_render_deadline_starts_when_candidate_enters_awaiting_render(
    run_repositories,
) -> None:
    lifecycle, _, _, _ = _services(run_repositories)
    conversation = lifecycle.create_conversation(title="Render deadline")
    run = run_async_in_thread(
        lifecycle.create_run(
            conversation.conversation_id,
            AgentRunCreateRequest(message="Show Rome"),
        )
    )
    run_repositories["runs"].prepare_render(
        run.run_id,
        run.run_version,
        {
            "status": "pending",
            "map_session_id": "map-session-deadline",
            "collection_revision": 1,
            "pending_response": {
                "map_session": {
                    "session_id": "map-session-deadline",
                    "overlay_collection": {"collection_id": "active-map", "revision": 1, "instances": []},
                }
            },
            "required_render_checks": {},
            "completion_requirements": [],
        },
    )

    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        record = session.get(AgentRunRecord, run.run_id)
        assert record is not None
        assert record.render_prepared_at is not None
        record.created_at = datetime.now(UTC) - timedelta(seconds=120)
        session.commit()

    assert run_repositories["runs"].expire_pending_render(
        conversation_id=conversation.conversation_id,
        run_id=run.run_id,
        run_version=run.run_version,
        timeout_seconds=90,
    ) is None

    with run_repositories["runs"]._session_factory() as session:  # noqa: SLF001
        record = session.get(AgentRunRecord, run.run_id)
        assert record is not None
        record.render_prepared_at = datetime.now(UTC) - timedelta(seconds=120)
        session.commit()

    expired = run_repositories["runs"].expire_pending_render(
        conversation_id=conversation.conversation_id,
        run_id=run.run_id,
        run_version=run.run_version,
        timeout_seconds=90,
    )
    assert expired is not None
    assert expired.presentation_status == "render_timeout"
    assert expired.presentation is not None
    assert expired.presentation["status"] == "render_timeout"
    assert "pending_response" not in expired.presentation
    timeout_events = run_repositories["events"].list_events(run.run_id)
    assert [event.type for event in timeout_events] == [RunEventType.ERROR]
    assert timeout_events[0].payload == {
        "code": "render_timeout",
        "message": (
            "The browser did not acknowledge the prepared map before the render deadline."
        ),
        "presentation_status": "render_timeout",
        "state": "failed",
    }
