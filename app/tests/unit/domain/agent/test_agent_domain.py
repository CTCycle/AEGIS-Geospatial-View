from __future__ import annotations
import pytest
from pydantic import ValidationError
from server.domain.agent.capability_route import AgentPhase, AgentRunState, CapabilityDomain, CapabilityRoute
from server.domain.agent.conversation import ConversationState, PendingClarification
from server.domain.agent.map_plan import MapPlan
from server.domain.agent.tool_result import ModelObservation, ToolExecutionError, ToolExecutionMetadata, ToolResult, ValidationIssue

# --- test_capability_route.py ---



###############################################################################
def test_capability_route_is_bounded_and_strict() -> None:
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        secondary_domains=[CapabilityDomain.MAP_RENDERING],
        task_mode="execute",
        presentation="both",
        location_mode="target",
        capability_queries=["hospitals"],
    )

    assert route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert route.presentation == "both"

    with pytest.raises(ValidationError):
        CapabilityRoute(
            primary_domain="not-a-domain",
            task_mode="execute",
            presentation="text",
            location_mode="none",
        )

    with pytest.raises(ValidationError):
        CapabilityRoute(
            primary_domain="conversation",
            task_mode="execute",
            presentation="text",
            location_mode="none",
            unexpected=True,
        )

###############################################################################
def test_agent_state_tracks_native_loop_counters() -> None:
    state = AgentRunState(
        request_id="req-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Find Zurich.",
    )

    assert state.phase is AgentPhase.ROUTE_REQUEST
    assert state.tool_results == []
    with pytest.raises(ValidationError):
        AgentRunState(
            request_id="req-1",
            conversation_id="conversation-1",
            phase=AgentPhase.ROUTE_REQUEST,
            user_message="Find Zurich.",
            unexpected=True,
        )

###############################################################################
def test_agent_run_state_is_the_single_checkpointable_native_state() -> None:
    state = AgentRunState(
        request_id="req-1",
        run_id="run-1",
        run_version=3,
        conversation_revision=7,
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Find Zurich.",
    )

    restored = AgentRunState.from_checkpoint(state.checkpoint())

    assert restored.run_version == 3
    assert restored.conversation_revision == 7
    assert restored.request_id == state.request_id

###############################################################################
def test_exposure_trace_iteration_is_checkpointable_after_render_resume() -> None:
    state = AgentRunState(
        request_id="req-render",
        conversation_id="conversation-render",
        phase=AgentPhase.AWAIT_RENDER,
        user_message="Show a raster layer.",
        exposure_trace=[
            {
                "iteration": 5,
                "phase": "build_tool_context",
                "tool": "apply_map_plan",
            }
        ],
    )

    restored = AgentRunState.from_checkpoint(state.checkpoint())

    assert restored.exposure_trace[0]["iteration"] == 5

# --- test_conversation.py ---



###############################################################################
def test_other_conversation_state_schema_versions_are_rejected() -> None:
    for schema_version in (1, 3):
        with pytest.raises(ValueError, match="schema_version"):
            ConversationState.from_persisted(
                "conversation-future",
                {
                    "schema_version": schema_version,
                    "conversation_id": "conversation-future",
                },
            )

###############################################################################
def test_unrelated_turn_defers_but_does_not_delete_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-2",
        {
            "conversation_id": "conversation-2",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
                "scope_terms": ["lake", "bracciano"],
            },
        },
    )

    projection = state.context_projection("Add an environmental layer")
    assert projection["pending_clarification"] is None
    assert state.pending_clarification is not None
    assert state.pending_clarification.question.endswith("Bracciano?")

###############################################################################
def test_generic_unrelated_turn_does_not_answer_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-3",
        {
            "conversation_id": "conversation-3",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
            },
        },
    )

    assert state.context_projection("Hello")["pending_clarification"] is None
    deferred = state.clarification_after_turn("Hello")
    assert deferred is not None
    assert deferred.status == "deferred"

###############################################################################
def test_direct_answer_resolves_and_preserves_terminal_clarification() -> None:
    state = ConversationState.from_persisted(
        "conversation-4",
        {
            "conversation_id": "conversation-4",
            "pending_clarification": {
                "question": "Which country contains Lake Bracciano?",
                "source_turn_index": 1,
            },
        },
    )

    answered = state.clarification_after_turn("Italy")
    assert answered is not None
    assert answered.status == "answered"
    answered_state = state.model_copy(update={"pending_clarification": answered})
    preserved = answered_state.clarification_after_turn("Hello")
    assert preserved is not None
    assert preserved.status == "answered"

###############################################################################
def test_infrastructure_option_matching_uses_word_boundaries() -> None:
    clarification = PendingClarification.from_turn(
        "Which infrastructure category do you need?",
        source_turn_index=1,
        source_text="Show infrastructure in Rome",
    )

    assert clarification.match_option("EV charging stations") == "ev_charging"
    assert clarification.match_option("level crossings") is None

# --- test_map_plan.py ---



###############################################################################
def test_map_plan_parses_discriminated_actions() -> None:
    plan = MapPlan.model_validate(
        {
            "expected_collection_revision": 7,
            "actions": [
                {
                    "action": "set_layer_opacity",
                    "instance_id": "traffic:zurich",
                    "opacity": 0.5,
                },
                {
                    "action": "set_viewport",
                    "strategy": "preserve_current",
                },
            ],
        }
    )

    assert plan.actions[0].action == "set_layer_opacity"
    assert plan.actions[1].action == "set_viewport"

###############################################################################
@pytest.mark.parametrize(
    "payload",
    [
        {
            "expected_collection_revision": 0,
            "actions": [
                {
                    "action": "set_layer_opacity",
                    "instance_id": "traffic",
                    "opacity": 1.1,
                }
            ],
        },
        {
            "expected_collection_revision": 0,
            "actions": [{"action": "unknown_action"}],
        },
        {
            "expected_collection_revision": 0,
            "actions": [
                {
                    "action": "set_basemap",
                    "capability_id": "osm",
                    "unexpected": True,
                }
            ],
        },
    ],
)
def test_map_plan_rejects_invalid_actions(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MapPlan.model_validate(payload)

# --- test_tool_result.py ---



###############################################################################
def test_tool_result_has_one_strict_model_visible_shape() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="resolve_geospatial_location",
        status="success",
        summary="Resolved Zurich.",
        metadata=ToolExecutionMetadata(duration_ms=12),
    )

    assert result.status == "success"
    assert result.metadata.duration_ms == 12

    with pytest.raises(ValidationError):
        ToolResult(
            call_id="call-1",
            tool_name="resolve_geospatial_location",
            status="not-a-status",
            summary="bad",
            metadata=ToolExecutionMetadata(duration_ms=0),
        )

    with pytest.raises(ValidationError):
        ToolResult(
            call_id="call-1",
            tool_name="resolve_geospatial_location",
            status="failed",
            summary="bad",
            metadata=ToolExecutionMetadata(duration_ms=0),
            unexpected=True,
        )

###############################################################################
def test_tool_execution_error_restricts_recovery_and_issue_shape() -> None:
    error = ToolExecutionError(
        error_type="schema_validation",
        code="missing_query",
        message="The query is required.",
        retryable=False,
        recovery="correct_arguments",
        validation_errors=[
            ValidationIssue(path="query", code="missing", message="Required.")
        ],
    )

    assert error.validation_errors[0].path == "query"
    with pytest.raises(ValidationError):
        ToolExecutionError(
            error_type="schema_validation",
            code="bad",
            message="bad",
            retryable=False,
            recovery="retry_forever",
        )

###############################################################################
def test_model_observation_keeps_semantic_outcome_and_caps_raw_features() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="execute_geospatial_capability",
        status="success",
        summary="Returned 40 features.",
        semantic_outcome="resolved",
        data={
            "capability_id": "places:hospitals",
            "feature_count": 40,
            "features": [{"geometry": {"coordinates": [1, 2]}}] * 500,
            "warnings": ["Source is stale."],
        },
        evidence_refs=["evidence-1"],
        metadata=ToolExecutionMetadata(
            capability_id="places:hospitals",
            provider_id="overpass",
            duration_ms=12,
        ),
    )

    observation = ModelObservation.from_tool_result(result, max_chars=1200)

    assert observation.semantic_outcome == "resolved"
    assert observation.evidence_refs == ["evidence-1"]
    assert isinstance(observation.result, dict)
    assert len(observation.result["features"]) <= 24
    assert len(str(observation.model_dump_json())) <= 3000