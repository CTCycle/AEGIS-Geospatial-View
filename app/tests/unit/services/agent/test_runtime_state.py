from __future__ import annotations

import pytest

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
from server.services.agent.tool_registry import ToolRegistry
from server.services.agent.conversation_state import ConversationTaskStateService


def test_task_graph_requires_successful_predecessors() -> None:
    tasks = [
        AgentTask(id="resolve", description="Resolve place", status="failed"),
        AgentTask(id="fetch", description="Fetch data", depends_on=["resolve"]),
    ]
    validate_task_graph(tasks)
    assert runnable_tasks(tasks) == []
    assert block_tasks_with_failed_dependencies(tasks) == 1
    assert tasks[1].status == "blocked"
    assert evaluate_completion(
        AgentThreadState(conversation_id="c", goal=AgentGoal(id="g", text="x"), tasks=tasks)
    ) == "required_task_failed"


def test_task_graph_rejects_cycles() -> None:
    tasks = [
        AgentTask(id="a", description="A", depends_on=["b"]),
        AgentTask(id="b", description="B", depends_on=["a"]),
    ]
    with pytest.raises(RuntimeValidationError, match="cycle"):
        validate_task_graph(tasks)


def test_fingerprints_are_canonical_and_scope_invalidation_is_selective() -> None:
    assert canonical_call_fingerprint("search", {"b": 2, "a": 1}) == canonical_call_fingerprint(
        "search", {"a": 1, "b": 2}
    )
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
    assert [item.name for item in select_tools(profiles, require_rendering=True)] == ["render"]


def test_domain_validation_rejects_invalid_bounds_and_temporal_ranges() -> None:
    assert "between -90" in (ToolRegistry._validate_domain_arguments({"latitude": 91}) or "")
    assert "ordered" in (
        ToolRegistry._validate_domain_arguments({"bbox": [10, 1, -10, 2]}) or ""
    )


def test_steering_delta_supersedes_scope_work_and_appends_datasets() -> None:
    state = AgentThreadState(
        conversation_id="c",
        active_task_id="resolve",
        evidence_refs=["weather-layer"],
        tasks=[
            AgentTask(id="resolve", description="Resolve", kind="location_resolution", status="completed"),
            AgentTask(
                id="weather",
                description="Weather",
                kind="weather",
                status="completed",
                output_refs=["weather-layer"],
            ),
        ],
    )
    class Delta:
        kind = "exclusion"
        text = "Exclude the western side"
    apply_steering_delta(state, Delta())
    assert state.tasks[0].status == "completed"
    assert state.tasks[1].status == "superseded"
    assert state.evidence_refs == []
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


def test_hydration_accepts_v2_only_and_restores_active_task() -> None:
    service = ConversationTaskStateService()
    service.hydrate(
        "conversation",
        {
            "schema_version": 2,
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
    with pytest.raises(ValueError, match="schema_version"):
        service.hydrate("conversation", {"conversation_key": "conversation", "tasks": []})
