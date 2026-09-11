from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.execution import AgentExecutionContext
from server.domain.agent.interpretation import (
    CanonicalRequestInterpretation,
    CanonicalTarget,
)
from server.domain.agent.pipeline import ToolPlanStep
from server.services.agent.tool_plan_executor import ToolPlanExecutor

###############################################################################
def _step() -> ToolPlanStep:
    return ToolPlanStep(
        step_id="step-1",
        tool_name="execute_geospatial_capability",
        capability_id="usgs_earthquakes",
        reason="test",
        target_id="target-1",
        analysis_scope="bbox",
    )

###############################################################################
def test_invalid_map_coordinates_are_rejected_before_commit() -> None:
    data = {
        "ok": True,
        "capability_id": "usgs_earthquakes",
        "map_session": {
            "resolved_location": {
                "label": "invalid",
                "latitude": 140,
                "longitude": 10,
            }
        },
    }

    assert ToolPlanExecutor._validate_result(_step(), data) == (
        "Tool output contains invalid EPSG:4326 coordinates."
    )

###############################################################################
def test_reversed_or_malformed_bbox_is_rejected() -> None:
    data = {
        "ok": True,
        "capability_id": "usgs_earthquakes",
        "map_session": {
            "resolved_location": {"label": "Rome", "latitude": 41.9, "longitude": 12.5},
            "bounds": [12.5, 42.0, 12.0, 41.0],
        },
    }

    assert ToolPlanExecutor._validate_result(_step(), data) == (
        "Tool output contains an invalid [west, south, east, north] bbox."
    )

###############################################################################
def test_wrong_target_and_scope_are_rejected_when_declared() -> None:
    wrong_target = {
        "ok": True,
        "capability_id": "usgs_earthquakes",
        "target_id": "target-2",
        "analysis_scope": "bbox",
    }
    wrong_scope = {
        "ok": True,
        "capability_id": "usgs_earthquakes",
        "target_id": "target-1",
        "analysis_scope": "radius",
    }

    assert "target" in (ToolPlanExecutor._validate_result(_step(), wrong_target) or "")
    assert "scope" in (ToolPlanExecutor._validate_result(_step(), wrong_scope) or "")

###############################################################################
def test_step_context_binds_each_multi_target_to_its_own_location() -> None:
    paris = ResolvedLocation(
        label="Paris, France",
        latitude=48.8566,
        longitude=2.3522,
        location_type="city",
    )
    london = ResolvedLocation(
        label="London, United Kingdom",
        latitude=51.5074,
        longitude=-0.1278,
        location_type="city",
    )
    canonical = CanonicalRequestInterpretation(
        request_id="compare-1",
        primary_intent="compare",
        targets=[
            CanonicalTarget(
                target_id="target-paris",
                original_text="Paris",
                entity_kind="city",
                resolved_location=paris,
            ),
            CanonicalTarget(
                target_id="target-london",
                original_text="London",
                entity_kind="city",
                resolved_location=london,
                peer=True,
            ),
        ],
    )
    context = AgentExecutionContext(
        resolved_location=paris,
        canonical_request=canonical,
        metadata={"target_id": "target-paris"},
    )

    bound = ToolPlanExecutor._context_for_step(
        context,
        ToolPlanStep(
            step_id="london-step",
            tool_name="execute_geospatial_capability",
            capability_id="flooding",
            reason="compare the London target",
            target_id="target-london",
            analysis_scope="bbox",
        ),
    )

    assert bound.resolved_location is london
    assert bound.metadata["target_id"] == "target-london"
    assert bound.resolved_location is not context.resolved_location
