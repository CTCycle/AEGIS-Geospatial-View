from __future__ import annotations

from typing import Any, cast

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentPhase,
    AgentState,
    CapabilityRoute,
)
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.agent.capability_router import CapabilityRouter
from server.services.geospatial.capability_registry import CapabilityRegistry


class _Runtime:
    def __init__(self, *, disabled: set[str] | None = None) -> None:
        self.disabled = disabled or set()

    def is_enabled(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

    def access_available(self, capability_id: str) -> bool:
        return capability_id not in self.disabled


def _router(runtime: _Runtime | None = None) -> CapabilityRouter:
    registry = CapabilityRegistry.from_catalog_snapshot(
        GeospatialManifestSnapshot(
        providers=(),
            basemaps=[
                {
                    "id": "osm_default",
                    "name": "OpenStreetMap",
                    "provider": "osm_tiles",
                    "capabilityKind": "basemap",
                    "agenticUse": {"domains": ["map_rendering"]},
                }
            ],
            overlays=[
                {
                    "id": "traffic",
                    "name": "Traffic",
                    "provider": "test",
                    "capabilityKind": "vector-overlay",
                    "description": "Traffic incidents",
                    "capabilities": ["traffic"],
                    "agenticUse": {"domains": ["data_retrieval"]},
                }
            ],
            cameras=[],
            transit=[],
            tools=[],
            runtime_profiles=(),
        )
    )
    return CapabilityRouter(
        capability_registry=registry,
        runtime_registry=cast(Any, runtime or _Runtime()),
    )


def _state(*, active_map: bool = False) -> AgentState:
    state = AgentState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Show traffic.",
    )
    if active_map:
        state.active_map_session = cast(Any, object())
    return state


def _route(**overrides: Any) -> CapabilityRoute:
    values: dict[str, Any] = {
        "primary_domain": CapabilityDomain.DATA_RETRIEVAL,
        "task_mode": "execute",
        "presentation": "map",
        "requires_location": True,
        "capability_queries": ["traffic"],
    }
    values.update(overrides)
    return CapabilityRoute.model_validate(values)


def test_router_shortlists_without_selecting_final_arguments() -> None:
    decision = _router().validate_route(
        _route(), user_message="Show traffic in Zurich.", active_state=_state()
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]
    assert "radius_m" not in decision.route.model_dump()


def test_router_rejects_hallucinated_ids_and_reports_no_capability() -> None:
    decision = _router().validate_route(
        _route(explicit_capability_ids=["not-in-catalog"]),
        user_message="Use not-in-catalog.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["not-in-catalog"]
    assert "unknown_capability_id" in decision.reason_codes


def test_router_requires_active_map_for_map_state_follow_up() -> None:
    decision = _router().validate_route(
        _route(primary_domain=CapabilityDomain.MAP_STATE, requires_location=False),
        user_message="Hide the layer.",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert "active_map_required" in decision.reason_codes


def test_router_handles_runtime_disabled_explicit_candidate() -> None:
    decision = _router(_Runtime(disabled={"traffic"})).validate_route(
        _route(explicit_capability_ids=["traffic"]),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["traffic"]
    assert "capability_disabled" in decision.reason_codes


def test_router_normalizes_new_map_location_prerequisite_and_hides_basemap_tools() -> None:
    decision = _router().validate_route(
        _route(requires_location=False),
        user_message="Show traffic on a new map.",
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.requires_location is True
    assert "location_required_for_new_map" in decision.reason_codes
    assert "osm_default" not in decision.capability_ids
