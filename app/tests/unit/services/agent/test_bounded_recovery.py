from __future__ import annotations

from server.domain.agent.capability_route import AgentGoal, AgentPhase, AgentRunState
from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.tool_result import ToolExecutionError, ToolExecutionMetadata, ToolResult
from server.services.agent.agent_loop import AgentLoop
from server.services.agent.native_tools import _bind_execute_request  # pyright: ignore[reportPrivateUsage]
from server.services.agent.policy_engine import _is_substitute  # pyright: ignore[reportPrivateUsage]
from server.services.agent.tool_definitions import ExecuteCapabilityInput
from server.services.agent.tool_handlers.evidence import _apply_operations  # pyright: ignore[reportPrivateUsage]


###############################################################################
def _state(places: dict[str, str]) -> AgentRunState:
    state = AgentRunState(
        request_id="r", conversation_id="c", phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Compare Lugano and Milan temperatures",
    )
    state.goal = AgentGoal(
        goal=state.user_message, task_mode="execute", presentation="text", operation="compare",
        location_mode="search_area", target_ids=list(places),
    )
    state.location_refs = {
        name.casefold(): ResolvedLocation(label=name, latitude=45.0, longitude=9.0, location_type=kind)
        for name, kind in places.items()
    }
    return state


###############################################################################
def test_per_city_value_request_is_a_point_query_and_a_region_stays_an_area() -> None:
    cities = _state({"Lugano": "city", "Milan": "city"})
    region = _state({"Lombardy": "region"})

    point = _bind_execute_request(ExecuteCapabilityInput(capability_id="w", location_ref="Lugano"), cities)
    area = _bind_execute_request(ExecuteCapabilityInput(capability_id="w", location_ref="Lombardy"), region)

    assert "sampling" not in point.arguments
    assert area.arguments["sampling"] == "area"


###############################################################################
def _rate_limited() -> ToolResult:
    return ToolResult(
        call_id="x", tool_name="execute_geospatial_capability", status="failed", summary="limited",
        error=ToolExecutionError(
            error_type="rate_limit", code="provider_rate_limit", message="limited",
            retryable=False, recovery="retry_transport",
        ),
        metadata=ToolExecutionMetadata(capability_id="open_meteo", duration_ms=1),
    )


###############################################################################
def test_rate_limit_is_retried_once_then_the_target_fails_without_a_pivot() -> None:
    state = _state({"Lugano": "city", "Milan": "city"})
    state.capability_ids = ["open_meteo"]

    AgentLoop._apply_result(state, _rate_limited(), target="milan")  # pyright: ignore[reportPrivateUsage]
    assert state.excluded_capability_ids == [] and state.capability_ids == ["open_meteo"]
    assert state.failed_data_targets == {}

    AgentLoop._apply_result(state, _rate_limited(), target="milan")  # pyright: ignore[reportPrivateUsage]
    assert state.excluded_capability_ids == ["open_meteo"]
    assert state.failed_data_targets == {"milan": "open_meteo"}


###############################################################################
def test_substitute_must_supply_the_same_variable_and_kind() -> None:
    def manifest(hints: list[str], render: str) -> dict[str, object]:
        return {"agenticUse": {"plannerHints": hints}, "executionContract": {"render_support": render}}

    failed = manifest(["temperature"], "vector")

    assert _is_substitute(manifest(["temperature", "wind"], "vector"), failed)
    assert not _is_substitute(manifest(["temperature"], "raster"), failed)
    assert not _is_substitute(manifest(["precipitation"], "vector"), failed)


###############################################################################
def test_transform_error_lists_the_available_fields() -> None:
    records = [{"properties": {"temperature_2m": 5.0, "name": "Vienna", "nested": {"a": 1}}}]

    _, error = _apply_operations(records, [{"op": "sort", "field": "temp"}])

    assert error is not None
    assert "temperature_2m" in error and "name" in error and "nested" not in error


###############################################################################
def test_a_projection_keeps_a_measurement_named_by_its_summary_path() -> None:
    # S12-T4: summaries show observations.temperature_2m, records store it flat.
    records = [
        {"name": "Prague", "latitude": 50.1, "longitude": 14.4, "temperature_2m": 0.8},
        {"name": "Vienna", "latitude": 48.2, "longitude": 16.4, "temperature_2m": 4.8},
    ]
    path = "observations.temperature_2m"

    result, error = _apply_operations(records, [
        {"op": "field_projection", "fields": ["name", path]},
        {"op": "sort", "field": path, "descending": True},
    ])

    assert error is None
    assert [(item["name"], item["temperature_2m"]) for item in result] == [("Vienna", 4.8), ("Prague", 0.8)]
