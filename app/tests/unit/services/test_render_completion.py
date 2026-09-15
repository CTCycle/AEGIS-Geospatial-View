from __future__ import annotations

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tests.conftest import run_async_in_thread
from server.contracts.geospatial import (
    MapSession,
    OverlayCollectionState,
    OverlayInstance,
    ViewportPolicy,
)
from server.contracts.events import RunEventType
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.capability_route import AgentGoal, CompletionContract
from server.domain.realtime import RealtimeRenderAckPayload
from server.repositories.agent_run_events import AgentRunEventRepository
from server.repositories.agent_runs import AgentRunRepository
from server.repositories.schemas.models import Base, ConversationRecord
from server.services.agent.completion import CompletionEvaluator
from server.services.agent_runs.events import RunEventPublisher
from server.services.agent_runs.render_completion import RenderCompletionService

###############################################################################
class _EventPublisher:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    # -------------------------------------------------------------------------
    async def publish(
        self,
        *,
        type: object,
        payload: dict[str, object],
        **_kwargs: object,
    ) -> None:
        self.events.append((str(type), dict(payload)))

###############################################################################
class _InMemoryBackend:

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
def render_context() -> tuple[AgentRunRepository, _EventPublisher, str, str]:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    conversation_id = "conversation-render"
    with backend.session() as session:
        session.add(ConversationRecord(id=conversation_id, title="Render"))
        session.commit()
    repository = AgentRunRepository(backend)
    run = repository.create_run(
        conversation_id,
        "Show Rome",
        "Show Rome",
        client_request_id="render-request-1",
    )
    publisher = _EventPublisher()
    return repository, publisher, conversation_id, run.run_id

###############################################################################
def _session(
    *instances: OverlayInstance,
    bounds: list[float] | None = None,
    payload: dict[str, object] | None = None,
) -> MapSession:
    location = ResolvedLocation(
        label="Rome, Italy",
        latitude=41.9028,
        longitude=12.4964,
        location_type="city",
        bbox=[12.3, 41.7, 12.7, 42.1],
    )
    return MapSession(
        session_id="map-session-1",
        resolved_location=location,
        basemap_id="osm_standard",
        viewport=ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=25_000,
            bbox=bounds or location.bbox,
        ),
        bounds=bounds or location.bbox,
        payload=dict(payload or {}),
        overlay_collection=OverlayCollectionState(
            collection_id="active-map",
            revision=4,
            instances=list(instances),
        ),
    )

###############################################################################
def _contract(*requirements: str) -> CompletionContract:
    return CompletionContract(
        operation="geospatial_data_retrieval",
        requirements=list(requirements),
        map_preparation_required=True,
    )


def _goal(
    *,
    temporal_scope: dict[str, object] | None = None,
    spatial_scope: list[dict[str, object]] | None = None,
) -> AgentGoal:
    return AgentGoal(
        goal="Show geospatial data in Rome",
        task_mode="execute",
        presentation="map",
        operation="geospatial_data_retrieval",
        requires_location=True,
        target_ids=["target-rome"],
        temporal_scope=temporal_scope or {},
        spatial_scope=spatial_scope or [],
    )

###############################################################################
def test_metadata_only_overlay_cannot_satisfy_renderable_geometry() -> None:
    metadata = OverlayInstance(
        instance_id="weather-1",
        capability_id="openmeteo_weather_forecast",
        label="Weather",
        provider="open-meteo",
        overlay_type="metadata",
        rendering_mode="metadata-only",
        descriptor={"result_type": "metadata"},
    )
    requirements = CompletionEvaluator.native_candidate_requirements(
        completion_contract=_contract(),
        goal=_goal(),
        map_session=_session(metadata),
    )

    map_candidate = next(item for item in requirements if item.name == "map_candidate_prepared")
    assert map_candidate.status == "satisfied"
    assert RenderCompletionService.requires_browser_ack(_session(metadata)) is False

###############################################################################
def test_location_only_map_still_requires_browser_ack() -> None:
    assert RenderCompletionService.requires_browser_ack(_session()) is True

###############################################################################
def test_unavailable_provider_is_not_treated_as_metadata_only() -> None:
    unavailable = OverlayInstance(
        instance_id="fires-1",
        capability_id="nasa_firms_active_fires",
        label="Active fires",
        provider="nasa-firms",
        overlay_type="geojson",
        rendering_mode="metadata-only",
        descriptor={"result_status": "unavailable", "result_type": "features"},
    )
    candidate = _session(unavailable)
    assert RenderCompletionService.requires_browser_ack(candidate) is False
    assert RenderCompletionService.has_blocking_data_failure(candidate) is True

    render_unavailable = candidate.model_copy(deep=True)
    render_unavailable.overlay_collection.instances[0].rendering_mode = "geojson"
    render_unavailable.overlay_collection.instances[0].descriptor = {
        "render_status": "unavailable",
        "result_type": "features",
    }
    assert RenderCompletionService.requires_browser_ack(render_unavailable) is True
    assert RenderCompletionService.has_blocking_data_failure(render_unavailable) is True
    requirements = CompletionEvaluator.native_candidate_requirements(
        completion_contract=_contract("required_data_retrieved"),
        goal=_goal(),
        map_session=render_unavailable,
    )
    assert next(
        item for item in requirements if item.name == "required_data_retrieved"
    ).status == "failed"

###############################################################################
def test_valid_empty_result_with_bounds_can_render_analysis_area() -> None:
    requirements = CompletionEvaluator.native_candidate_requirements(
        completion_contract=_contract(),
        goal=_goal(),
        map_session=_session(payload={"result_status": "valid_empty"}),
    )

    renderable = next(item for item in requirements if item.name == "map_candidate_prepared")
    assert renderable.status == "satisfied"

###############################################################################
def test_explicit_scope_and_time_require_descriptor_evidence() -> None:
    goal = _goal(
        temporal_scope={
            "mode": "historical",
            "start_time_iso": "2026-08-01T00:00:00+00:00",
            "end_time_iso": "2026-08-02T00:00:00+00:00",
        },
        spatial_scope=[
            {
                "kind": "radius",
                "relationship": "within_distance",
                "target_refs": ["target-rome"],
                "distance_m": 5_000,
            }
        ],
    )
    candidate = _session(
        OverlayInstance(
            instance_id="earthquake-rome",
            capability_id="usgs_earthquakes",
            label="Earthquakes",
            provider="usgs",
            overlay_type="geojson",
            rendering_mode="geojson",
            descriptor={
                "result_type": "feature_collection",
                "data": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "geometry": {
                                "type": "Point",
                                "coordinates": [12.5, 41.9],
                            },
                        }
                    ],
                },
            },
        )
    )

    requirements = CompletionEvaluator.native_candidate_requirements(
        completion_contract=_contract("required_data_retrieved", "temporal_scope_applied", "spatial_scope_applied"),
        goal=goal,
        map_session=candidate,
    )
    assert next(item for item in requirements if item.name == "spatial_scope_applied").status == "pending"

    candidate.overlay_collection.instances[0].descriptor.update(
        {
            "analysis_scope": "radius",
            "temporal_mode": "historical",
        }
    )
    requirements = CompletionEvaluator.native_candidate_requirements(
        completion_contract=_contract("required_data_retrieved", "temporal_scope_applied", "spatial_scope_applied"),
        goal=goal,
        map_session=candidate,
    )
    assert next(item for item in requirements if item.name == "temporal_scope_applied").status == "satisfied"

###############################################################################
def test_acknowledgment_payload_is_bounded_and_requires_valid_viewport() -> None:
    payload = RealtimeRenderAckPayload(
        run_id="run-1",
        run_version=1,
        map_session_id="map-session-1",
        collection_revision=4,
        status="ready",
        viewport_bounds=[12.3, 41.7, 12.7, 42.1],
        checks={
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
    )
    assert payload.viewport_bounds == [12.3, 41.7, 12.7, 42.1]

    raster_payload = RealtimeRenderAckPayload(
        run_id="run-raster",
        run_version=1,
        map_session_id="map-session-raster",
        collection_revision=0,
        status="ready",
        viewport_bounds=[-105.2, 39.5, -104.7, 40.1],
        overlay_results=[
            {
                "overlay_id": "noaa-radar-denver",
                "capability_id": "noaa_radar",
                "source_present": True,
                "layer_present": True,
                "loaded": True,
                "metadata_only": False,
                "visibility_matches": True,
                "style_valid": True,
                "zoom_range_valid": True,
                "rendered_feature_count": None,
            }
        ],
    )
    assert raster_payload.overlay_results[0]["rendered_feature_count"] is None

    with pytest.raises(ValueError):
        RealtimeRenderAckPayload(
            run_id="run-1",
            run_version=1,
            map_session_id="map-session-1",
            collection_revision=4,
            status="ready",
            viewport_bounds=[12.3, 42.0, 12.7, 41.0],
        )

    with pytest.raises(ValueError):
        RealtimeRenderAckPayload(
            run_id="run-1",
            run_version=1,
            map_session_id="map-session-1",
            collection_revision=4,
            status="ready",
            checks={
                "required_sources_loaded": True,
                "required_layers_present": True,
                "viewport_valid": True,
            },
        )

###############################################################################
def test_matching_render_ack_promotes_once_and_replay_is_idempotent(
    render_context,
) -> None:
    repository, publisher, conversation_id, run_id = render_context
    candidate = _session(
        OverlayInstance(
            instance_id="earthquake-rome",
            capability_id="usgs_earthquakes",
            label="Earthquakes",
            provider="usgs",
            overlay_type="geojson",
            rendering_mode="geojson",
            descriptor={
                "result_type": "feature_collection",
                "data": {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "id": "quake-1",
                            "geometry": {"type": "Point", "coordinates": [12.5, 41.9]},
                            "properties": {"magnitude": 4.2},
                        }
                    ],
                },
            },
        )
    )
    service = RenderCompletionService(
        run_repository=repository,
        event_publisher=publisher,  # type: ignore[arg-type]
    )
    presentation, prepared = service.prepare(
        run_id=run_id,
        run_version=1,
        response_payload={
            "assistant_message": "Data prepared; the map is loading.",
            "map_session": candidate.model_dump(mode="json"),
            "memory_snapshot": {},
            "conversation_state": {
                "conversation_id": conversation_id,
                "revision": 0,
            },
        },
    )
    assert prepared is True
    assert presentation["status"] == "pending"

    acknowledgment = RealtimeRenderAckPayload(
        run_id=run_id,
        run_version=1,
        map_session_id=candidate.session_id,
        collection_revision=candidate.overlay_collection.revision,
        status="ready",
        viewport_bounds=candidate.bounds,
        checks={
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
        overlay_results=[
            {
                "overlay_id": "earthquake-rome",
                "source_present": True,
                "layer_present": True,
                "loaded": True,
                "visibility_matches": True,
                "rendered_feature_count": 1,
            }
        ],
    )
    first = run_async_in_thread(service.acknowledge(conversation_id, acknowledgment))
    assert first.duplicate is False
    assert first.state == "completed"
    assert first.presentation_status == "ready"
    assert [event[0] for event in publisher.events].count("completed") == 1

    second = run_async_in_thread(service.acknowledge(conversation_id, acknowledgment))
    assert second.duplicate is True
    assert [event[0] for event in publisher.events].count("completed") == 1

    with pytest.raises(ValueError, match="different render acknowledgment"):
        run_async_in_thread(
            service.acknowledge(
                conversation_id,
                acknowledgment.model_copy(update={"checks": {"viewport_valid": False}}),
            )
        )

###############################################################################
def test_render_ack_rejects_wrong_revision_and_vector_without_visible_features(
    render_context,
) -> None:
    repository, publisher, conversation_id, run_id = render_context
    candidate = _session(
        OverlayInstance(
            instance_id="earthquake-rome",
            capability_id="usgs_earthquakes",
            label="Earthquakes",
            provider="usgs",
            overlay_type="geojson",
            rendering_mode="geojson",
            descriptor={
                "result_type": "feature_collection",
                "data": {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
            },
        )
    )
    service = RenderCompletionService(
        run_repository=repository,
        event_publisher=publisher,  # type: ignore[arg-type]
    )
    presentation, prepared = service.prepare(
        run_id=run_id,
        run_version=1,
        response_payload={"map_session": candidate.model_dump(mode="json")},
    )
    assert prepared is True
    assert presentation["required_overlay_ids"] == ["earthquake-rome"]
    base_ack = {
        "run_id": run_id,
        "run_version": 1,
        "map_session_id": candidate.session_id,
        "collection_revision": candidate.overlay_collection.revision,
        "status": "ready",
        "viewport_bounds": candidate.bounds,
        "checks": {
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
        "overlay_results": [
            {
                "overlay_id": "earthquake-rome",
                "source_present": True,
                "layer_present": True,
                "loaded": True,
                "visibility_matches": True,
                "rendered_feature_count": 0,
            }
        ],
    }
    with pytest.raises(ValueError, match="does not match"):
        run_async_in_thread(
            service.acknowledge(
                conversation_id,
                RealtimeRenderAckPayload(
                    **{**base_ack, "collection_revision": candidate.overlay_collection.revision + 1}
                ),
            )
        )
    with pytest.raises(ValueError, match="visible"):
        run_async_in_thread(
            service.acknowledge(
                conversation_id,
                RealtimeRenderAckPayload(**base_ack),
            )
        )

###############################################################################
def test_render_ack_rejects_missing_required_data_even_with_analysis_bounds(
    render_context,
) -> None:
    repository, publisher, conversation_id, run_id = render_context
    candidate = _session()
    service = RenderCompletionService(
        run_repository=repository,
        event_publisher=publisher,  # type: ignore[arg-type]
    )
    _presentation, prepared = service.prepare(
        run_id=run_id,
        run_version=1,
        response_payload={
            "map_session": candidate.model_dump(mode="json"),
            "goal": AgentGoal(
                goal="Show earthquake data in Rome",
                task_mode="execute",
                presentation="map",
                operation="geospatial_data_retrieval",
                requires_location=True,
                target_ids=["target-rome"],
            ).model_dump(mode="json"),
            "completion_contract": _contract(
                "required_data_retrieved"
            ).model_dump(mode="json"),
        },
    )
    assert prepared is True
    with pytest.raises(ValueError, match="required_data_retrieved"):
        run_async_in_thread(
            service.acknowledge(
                conversation_id,
                RealtimeRenderAckPayload(
                    run_id=run_id,
                    run_version=1,
                    map_session_id=candidate.session_id,
                    collection_revision=candidate.overlay_collection.revision,
                    status="ready",
                    viewport_bounds=candidate.bounds,
                    checks={
                        "required_sources_loaded": True,
                        "required_layers_present": True,
                        "viewport_valid": True,
                    },
                ),
            )
        )

###############################################################################
def test_production_render_ack_persists_terminal_events_atomically() -> None:
    backend = _InMemoryBackend()
    Base.metadata.create_all(backend.engine)
    conversation_id = "conversation-render-atomic"
    with backend.session() as session:
        session.add(ConversationRecord(id=conversation_id, title="Render atomic"))
        session.commit()

    event_repository = AgentRunEventRepository(backend)
    repository = AgentRunRepository(backend, event_repository=event_repository)
    publisher = RunEventPublisher(event_repository)
    service = RenderCompletionService(
        run_repository=repository,
        event_publisher=publisher,
    )
    run = repository.create_run(
        conversation_id,
        "Show Rome",
        "Show Rome",
        client_request_id="render-atomic-1",
    )
    candidate = _session()
    _presentation, prepared = service.prepare(
        run_id=run.run_id,
        run_version=run.active_run_version,
        response_payload={
            "assistant_message": "Data prepared; the map is loading.",
            "map_session": candidate.model_dump(mode="json"),
            "memory_snapshot": {},
            "conversation_state": {
                "conversation_id": conversation_id,
                "revision": 0,
            },
        },
    )
    assert prepared is True

    acknowledgment = RealtimeRenderAckPayload(
        run_id=run.run_id,
        run_version=run.active_run_version,
        map_session_id=candidate.session_id,
        collection_revision=candidate.overlay_collection.revision,
        status="ready",
        viewport_bounds=candidate.bounds,
        checks={
            "required_sources_loaded": True,
            "required_layers_present": True,
            "viewport_valid": True,
        },
    )
    result = run_async_in_thread(service.acknowledge(conversation_id, acknowledgment))

    assert result.presentation_status == "ready"
    events = event_repository.list_events(run.run_id)
    assert [event.type for event in events] == [
        RunEventType.PROGRESS,
        RunEventType.ASSISTANT_TEXT_COMPLETED,
        RunEventType.COMPLETED,
    ]
    snapshot = repository.get_run(run.run_id)
    assert snapshot is not None
    assert snapshot.presentation_status == "ready"
    presentation = snapshot.presentation or {}
    assert len(presentation.get("durable_event_ids", [])) == 3
