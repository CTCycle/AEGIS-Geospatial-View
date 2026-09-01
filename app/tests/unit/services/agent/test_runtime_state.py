from __future__ import annotations

import pytest

from server.contracts.extraction import (
    ConversationContextSnapshot,
    NormalizedAction,
    TurnParseResult,
)
from server.domain.agent.runtime import (
    AgentGoal,
    AgentTask,
    AgentThreadState,
    GeographicScope,
    RuntimeValidationError,
    block_tasks_with_failed_dependencies,
    apply_steering_delta,
    canonical_call_fingerprint,
    evaluate_completion,
    invalidate_scope_evidence,
    runnable_tasks,
    select_tools,
    state_fingerprint,
    validate_task_graph,
    ToolCapabilityProfile,
)
from server.domain.agent.decision import (
    LocationResolutionProvenance,
    ResolvedLocation,
)
from server.contracts.geospatial import MapSession
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.conversation_state import ConversationTaskStateService


###############################################################################
def test_task_graph_requires_successful_predecessors() -> None:
    tasks = [
        AgentTask(id="resolve", description="Resolve place", status="failed"),
        AgentTask(id="fetch", description="Fetch data", depends_on=["resolve"]),
    ]
    validate_task_graph(tasks)
    assert runnable_tasks(tasks) == []
    assert block_tasks_with_failed_dependencies(tasks) == 1
    assert tasks[1].status == "blocked"
    assert (
        evaluate_completion(
            AgentThreadState(
                conversation_id="c", goal=AgentGoal(id="g", text="x"), tasks=tasks
            )
        )
        == "required_task_failed"
    )


###############################################################################
def test_task_graph_rejects_cycles() -> None:
    tasks = [
        AgentTask(id="a", description="A", depends_on=["b"]),
        AgentTask(id="b", description="B", depends_on=["a"]),
    ]
    with pytest.raises(RuntimeValidationError, match="cycle"):
        validate_task_graph(tasks)


###############################################################################
def test_fingerprints_are_canonical_and_scope_invalidation_is_selective() -> None:
    assert canonical_call_fingerprint(
        "search", {"b": 2, "a": 1}
    ) == canonical_call_fingerprint("search", {"a": 1, "b": 2})
    state = AgentThreadState(
        conversation_id="c",
        evidence_refs=["location", "weather", "air"],
    )
    change = invalidate_scope_evidence(
        state,
        invalidated_refs={"weather"},
        new_scope=GeographicScope(radius_m=50_000),
    )
    assert change.invalidated_evidence_refs == ("weather",)
    assert state.evidence_refs == ["location", "air"]
    assert state_fingerprint(state)


###############################################################################
def test_tool_selection_is_deterministic() -> None:
    profiles = [
        ToolCapabilityProfile(
            name="search",
            category="discovery",
            capabilities=["places"],
            supports_rendering=False,
        ),
        ToolCapabilityProfile(
            name="render",
            category="rendering",
            capabilities=["places"],
            supports_rendering=True,
        ),
    ]
    assert [item.name for item in select_tools(profiles, require_rendering=True)] == [
        "render"
    ]


###############################################################################
def test_domain_validation_rejects_invalid_bounds_and_temporal_ranges() -> None:
    assert "between -90" in (
        ToolRegistry._validate_domain_arguments({"latitude": 91}) or ""
    )
    assert "ordered" in (
        ToolRegistry._validate_domain_arguments({"bbox": [10, 1, -10, 2]}) or ""
    )


###############################################################################
def test_steering_delta_supersedes_scope_work_and_appends_datasets() -> None:
    state = AgentThreadState(
        conversation_id="c",
        active_task_id="resolve",
        evidence_refs=["weather-layer"],
        tasks=[
            AgentTask(
                id="resolve",
                description="Resolve",
                kind="location_resolution",
                status="completed",
            ),
            AgentTask(
                id="weather",
                description="Weather",
                kind="weather",
                status="completed",
                output_refs=["weather-layer"],
            ),
        ],
    )

    ###############################################################################
    class Delta:
        kind = "exclusion"
        text = "Exclude the western side"

    apply_steering_delta(state, Delta())
    assert state.tasks[0].status == "completed"
    assert state.tasks[1].status == "superseded"
    assert state.evidence_refs == []

    ###############################################################################
    class Add:
        kind = "add_dataset"
        text = "Add recent air quality"

    apply_steering_delta(state, Add())
    assert state.tasks[-1].kind == "dataset_enrichment"
    assert "reverse" in (
        ToolRegistry._validate_domain_arguments(
            {"start_time": "2026-02-02T00:00:00Z", "end_time": "2026-02-01T00:00:00Z"}
        )
        or ""
    )


###############################################################################
def test_hydration_accepts_v3_only_and_restores_active_task() -> None:
    service = ConversationTaskStateService()
    service.hydrate(
        "conversation",
        {
            "schema_version": 3,
            "conversation_key": "conversation",
            "current_task_id": "task-1",
            "goal": {"id": "task-1", "text": "Resolve Zurich"},
            "tasks": [
                {
                    "id": "task-1",
                    "description": "Resolve Zurich",
                    "kind": "location_resolution",
                    "status": "completed",
                    "depends_on": [],
                    "required": True,
                    "input_refs": [],
                    "output_refs": [],
                    "attempt_count": 1,
                    "last_failure": None,
                    "scope_revision": 0,
                }
            ],
            "geospatial_state": {},
            "evidence_refs": [],
            "active_map_session": None,
            "assumptions": [],
            "unresolved_questions": [],
            "conversation_summary": None,
        },
    )
    assert service.snapshot("conversation").current_task_id == "task-1"
    service.hydrate(
        "conversation",
        {"schema_version": 2, "conversation_key": "conversation", "tasks": []},
    )
    assert service.snapshot("conversation").current_task_id is None


###############################################################################
def test_terminal_task_update_finalizes_its_atomic_execution_graph() -> None:
    service = ConversationTaskStateService()
    turn = TurnParseResult(
        user_text="Find hospitals in Rome",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Find hospitals in Rome",
            requires_location=True,
        ),
        atomic_tasks=[
            {
                "id": "resolve-location",
                "summary": "Resolve Rome",
                "depends_on": [],
                "required": True,
            },
            {
                "id": "search-hospitals",
                "summary": "Search hospitals",
                "depends_on": ["resolve-location"],
                "required": True,
            },
        ],
    )

    task = service.start_task("conversation", turn, "geospatial_features")
    service.update_task("conversation", task.task_id, status="completed")

    snapshot = service.snapshot("conversation")
    assert {item.status for item in snapshot.tasks} == {"completed"}
    assert snapshot.goal is not None
    assert snapshot.goal.status == "completed"


###############################################################################
def test_verified_map_projects_location_sources_and_evidence_into_task_state() -> None:
    service = ConversationTaskStateService()
    turn = TurnParseResult(
        user_text="Find hospitals in Rome",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Find hospitals in Rome",
            requires_location=True,
        ),
    )
    task = service.start_task("conversation", turn, "geospatial_features")
    location = ResolvedLocation(
        label="Rome",
        latitude=41.9,
        longitude=12.5,
        provenance=LocationResolutionProvenance(
            provider="nominatim",
            source_url="https://nominatim.openstreetmap.org/search",
        ),
    )
    map_session = MapSession(
        session_id="map-rome",
        resolved_location=location,
        basemap_id="osm_default",
        viewport={
            "center_latitude": 41.9,
            "center_longitude": 12.5,
            "radius_m": 5000.0,
            "bbox": [12.4, 41.8, 12.6, 42.0],
        },
        bounds=[12.4, 41.8, 12.6, 42.0],
        basemap={"id": "osm_default", "provider": "osm"},
        overlay_collection={
            "instances": [
                {
                    "instance_id": "hospital-layer",
                    "capability_id": "overpass_poi_amenities",
                    "label": "Hospitals",
                    "provider": "overpass",
                    "overlay_type": "point",
                    "rendering_mode": "clustered-points",
                }
            ]
        },
    )

    service.update_task("conversation", task.task_id, status="completed")
    service.set_active_visualization(
        "conversation",
        map_session,
        tool_payload={
            "provider_events": [
                {
                    "capability_id": "location",
                    "provider": "nominatim",
                }
            ],
            "tool_results": [
                {
                    "is_error": False,
                    "provenance": {
                        "capability_id": "overpass_poi_amenities",
                        "provider": "overpass",
                    },
                }
            ],
        },
    )

    snapshot = service.snapshot("conversation")
    assert snapshot.geospatial_state.resolved_locations[0]["label"] == "Rome"
    assert snapshot.geospatial_state.geographic_scope.radius_m == 5000.0
    assert snapshot.geospatial_state.geographic_scope.bbox == [12.4, 41.8, 12.6, 42.0]
    assert snapshot.geospatial_state.layer_refs == ["hospital-layer"]
    assert snapshot.geospatial_state.data_source_refs == [
        "osm_default",
        "osm",
        "overpass_poi_amenities",
        "overpass",
        "location",
        "nominatim",
    ]
    assert snapshot.evidence_refs == [
        "location:nominatim",
        "overpass_poi_amenities:overpass",
    ]
