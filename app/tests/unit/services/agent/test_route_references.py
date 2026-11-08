from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState, CapabilityRoute
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.completion import uncovered_route_targets
from server.services.agent.route_references import route_reference_kind
from server.services.agent.tool_registry import unresolved_route_targets

RADAR = "RainViewer Recent Precipitation Radar"


###############################################################################
def _state(targets: list[str]) -> AgentRunState:
    state = AgentRunState(
        phase=AgentPhase.ROUTE_REQUEST, request_id="r", conversation_id="c", user_message="Remove it."
    )
    state.route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="map",
        location_mode="target",
        target_refs=targets,
    )
    layer = SimpleNamespace(instance_id="layer-1", capability_id="rainviewer_radar", label=RADAR)
    state.__dict__["active_map_session"] = cast(
        Any, SimpleNamespace(overlay_collection=SimpleNamespace(instances=[layer]))
    )
    return state


###############################################################################
def test_a_layer_capability_or_evidence_target_is_not_a_place_to_resolve() -> None:
    state = _state([RADAR, "evidence_1", "get_weather_forecast", "Tokyo"])
    state.evidence_refs.append("evidence_1")
    state.capability_ids.append("get_weather_forecast")

    assert route_reference_kind(RADAR, state) == "layer"
    assert route_reference_kind("evidence_1", state) == "evidence"
    assert route_reference_kind("get_weather_forecast", state) == "capability"
    assert unresolved_route_targets(state) == ["Tokyo"]


###############################################################################
def test_a_place_whose_name_merely_contains_a_layer_word_stays_a_place() -> None:
    state = _state(["Rainview Heights"])

    assert route_reference_kind("Rainview Heights", state) == "location"
    assert unresolved_route_targets(state) == ["Rainview Heights"]


###############################################################################
def test_a_resolved_place_wins_over_a_layer_spelling_the_same_name() -> None:
    state = _state([RADAR])
    state.location_refs[RADAR.casefold()] = ResolvedLocation(label=RADAR, latitude=1.0, longitude=2.0)

    assert route_reference_kind(RADAR, state) == "location"


###############################################################################
def test_a_layer_target_does_not_count_as_a_compared_place() -> None:
    # A compound request must not stay uncovered forever on its layer name.
    state = _state([RADAR, "Tokyo"])

    assert uncovered_route_targets(state) == []
