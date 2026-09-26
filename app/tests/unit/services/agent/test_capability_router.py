from __future__ import annotations

from typing import Any, cast

import pytest

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import (
    AgentPhase,
    AgentRunState,
    CapabilityRoute,
)
from server.domain.agent.decision import ResolvedLocation
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.agent.capability_router import (
    CapabilityRouter,
    build_location_map_fallback_route,
)
from server.services.geospatial.capability_registry import CapabilityRegistry

###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def __init__(self, *, disabled: set[str] | None = None) -> None:
        self.disabled = disabled or set()

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

###############################################################################
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
                    "executionContract": {
                        "supported_operations": ["show", "inspect"],
                        "supported_scope_kinds": ["bbox"],
                        "temporal_modes": ["current"],
                        "render_support": "vector",
                        "coverage": "global",
                    },
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

###############################################################################
def _state(*, active_map: bool = False) -> AgentRunState:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="Show traffic.",
    )
    if active_map:
        state.active_map_session = cast(Any, object())
    return state

###############################################################################
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

###############################################################################
def test_router_shortlists_without_selecting_final_arguments() -> None:
    decision = _router().validate_route(
        _route(), user_message="Show traffic in Zurich.", active_state=_state()
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]
    assert "radius_m" not in decision.route.model_dump()


def test_router_normalizes_radius_scope_to_provider_bbox_after_location_resolution() -> None:
    state = _state()
    state.location_refs["austin"] = ResolvedLocation(
        label="Austin, Texas",
        latitude=30.2672,
        longitude=-97.7431,
        bbox=[-98.1, 29.9, -97.4, 30.6],
        country="United States",
    )

    decision = _router().validate_route(
        _route(
            operation="retrieve_features",
            spatial_scope={
                "kind": "radius",
                "relationship": "around",
                "target_refs": ["Austin"],
                "distance_m": 25000,
            },
        ),
        user_message="Show traffic around Austin.",
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == ["traffic"]


###############################################################################
def test_router_rejects_answer_route_with_execution_intent() -> None:
    decision = _router().validate_route(
        CapabilityRoute(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            task_mode="answer",
            presentation="text",
            requires_location=False,
            capability_queries=["traffic"],
        ),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "rejected"
    assert "route_task_mode_requires_conversation_domain" in decision.reason_codes
    assert "route_task_mode_disallows_capability_queries" in decision.reason_codes


###############################################################################
def test_router_rejects_clarify_route_that_attempts_execution() -> None:
    decision = _router().validate_route(
        CapabilityRoute(
            primary_domain=CapabilityDomain.CONVERSATION,
            task_mode="clarify",
            presentation="text",
            requires_location=False,
            capability_queries=["traffic"],
            clarification_question="Which region do you mean?",
        ),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "rejected"
    assert "route_task_mode_disallows_capability_queries" in decision.reason_codes

###############################################################################
def test_router_rejects_hallucinated_ids_and_reports_no_capability() -> None:
    decision = _router().validate_route(
        _route(explicit_capability_ids=["not-in-catalog"]),
        user_message="Use not-in-catalog.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["not-in-catalog"]
    assert "unknown_capability_id" in decision.reason_codes

###############################################################################
def test_router_requires_active_map_for_map_state_follow_up() -> None:
    decision = _router().validate_route(
        _route(primary_domain=CapabilityDomain.MAP_STATE, requires_location=False),
        user_message="Hide the layer.",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert "active_map_required" in decision.reason_codes

###############################################################################
def test_router_handles_runtime_disabled_explicit_candidate() -> None:
    decision = _router(_Runtime(disabled={"traffic"})).validate_route(
        _route(explicit_capability_ids=["traffic"]),
        user_message="Show traffic.",
        active_state=_state(),
    )

    assert decision.status == "no_capability"
    assert decision.rejected_capability_ids == ["traffic"]
    assert "capability_disabled" in decision.reason_codes

###############################################################################
def test_router_opens_discovery_when_semantic_shortlist_is_empty() -> None:
    router = _router()
    router.capability_registry.shortlist = lambda **kwargs: []  # type: ignore[method-assign]

    decision = router.validate_route(
        _route(capability_queries=["obscure atmospheric index"]),
        user_message="Show an obscure atmospheric index.",
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert "discovery_required" in decision.reason_codes


###############################################################################
def test_broad_catalog_question_routes_to_unfiltered_capability_discovery() -> None:
    router = _router()
    router.capability_registry.shortlist = lambda **_kwargs: pytest.fail(  # type: ignore[method-assign]
        "catalog inventory must defer filtering until discovery"
    )
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
        secondary_domains=[CapabilityDomain.PLACE_SEARCH, CapabilityDomain.MAP_RENDERING],
        task_mode="execute",
        presentation="text",
        requires_location=True,
        capability_queries=["map data", "basemaps", "geospatial layers"],
        target_refs=["Florence, Italy"],
        spatial_scope={"kind": "point", "target_refs": ["Florence, Italy"]},
    )

    decision = router.validate_route(
        route,
        user_message=(
            "What map data can you show for Florence, Italy? "
            "Do not display a map or load a layer."
        ),
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert decision.route.operation == "discover_available_map_data"
    assert decision.route.capability_queries == []
    assert decision.capability_ids == []


###############################################################################
def test_router_clarifies_broad_infrastructure_category_before_shortlisting() -> None:
    for query in ("infrastructure", "infrastructure category", "infrastructure type"):
        decision = _router().validate_route(
            _route(
                operation="retrieve_infrastructure",
                capability_queries=[query],
            ),
            user_message=f"Show {query}.",
            active_state=_state(),
        )

        assert decision.status == "clarification"
        assert decision.capability_ids == []
        assert "ambiguous_infrastructure_category" in decision.reason_codes
        assert decision.clarification_question is not None
        assert "EV charging" in decision.clarification_question


###############################################################################
def test_raw_infrastructure_request_cannot_be_silently_guessed_into_subtype() -> None:
    decision = _router().validate_route(
        _route(
            operation="retrieve_infrastructure",
            capability_queries=["residential buildings"],
        ),
        user_message="Show infrastructure in Rome.",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert decision.capability_ids == []
    assert "ambiguous_infrastructure_category" in decision.reason_codes


###############################################################################
def test_router_returns_boundary_limitation_without_replacing_active_map() -> None:
    state = _state(active_map=True)
    state.location_refs["zurich"] = ResolvedLocation(
        label="Zurich",
        latitude=47.3769,
        longitude=8.5417,
        country="Switzerland",
    )
    active_map = state.active_map_session
    decision = _router().validate_route(
        _route(
            operation="show_boundary",
            capability_queries=["exact boundary"],
            spatial_scope={"kind": "administrative_geometry"},
        ),
        user_message="Show the exact boundary of Zurich.",
        active_state=state,
    )

    assert decision.status == "clarification"
    assert "unsupported_boundary_scope" in decision.reason_codes
    assert "active_map_preserved" in decision.reason_codes
    assert decision.clarification_question is not None
    assert "left the active map unchanged" in decision.clarification_question
    assert state.active_map_session is active_map

###############################################################################
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


###############################################################################
def test_location_map_fallback_route_is_limited_to_non_data_map_wording() -> None:
    fallback = build_location_map_fallback_route("Show me Springfield")

    assert fallback is not None
    assert fallback.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert fallback.secondary_domains == [CapabilityDomain.MAP_RENDERING]
    assert fallback.presentation == "map"
    assert fallback.requires_location is True

    assert build_location_map_fallback_route("Show hospitals near Springfield") is None


###############################################################################
def test_router_uses_active_map_for_layer_lifecycle_updates() -> None:
    state = _state(active_map=True)
    state.location_refs["current map"] = ResolvedLocation(
        label="Current map",
        latitude=35.0,
        longitude=139.0,
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            requires_location=True,
            capability_queries=["remove overlay layer", "map layer management"],
            operation="remove_layer",
            target_refs=["earthquake layer"],
        ),
        user_message="Remove the earthquake layer.",
        active_state=state,
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.requires_location is False
    assert "active_map_update_uses_current_map" in decision.reason_codes


###############################################################################
def test_router_normalizes_data_bearing_add_layer_routes_after_active_map() -> None:
    state = _state(active_map=True)
    state.location_refs["japan"] = ResolvedLocation(
        label="Japan",
        latitude=36.5748,
        longitude=139.2394,
        bbox=[122.7, 20.2, 154.2, 45.7],
    )
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_STATE,
            operation="add_layer",
            capability_queries=["traffic"],
            target_refs=["Traffic"],
            spatial_scope={
                "kind": "administrative_geometry",
                "relationship": "around",
                "target_refs": ["Japan"],
            },
        ),
        user_message="Add traffic around Japan.",
        active_state=state,
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_map_route_normalized" in decision.reason_codes


###############################################################################
def test_router_normalizes_new_data_bearing_map_routes() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.MAP_RENDERING,
            operation="add_layer",
            capability_queries=["land cover"],
            target_refs=["Mount Etna"],
            spatial_scope={
                "kind": "administrative_geometry",
                "relationship": "around",
                "target_refs": ["Mount Etna"],
            },
        ),
        user_message="Show land cover around Mount Etna.",
        active_state=_state(),
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_map_route_normalized" in decision.reason_codes


###############################################################################
def test_router_keeps_data_retrieval_on_poi_map_search_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            operation="search_places",
            capability_queries=["place search", "overpass_poi_amenities"],
        ),
        user_message="Show pharmacies in Rome, Italy.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert CapabilityDomain.MAP_RENDERING in decision.route.secondary_domains
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert "data_bearing_place_search_route_normalized" in decision.reason_codes
    assert "location_map_route_normalized" not in decision.reason_codes

###############################################################################
def test_router_adds_data_retrieval_to_text_only_poi_search_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            presentation="text",
            operation="search_places",
            capability_queries=["pharmacy"],
        ),
        user_message=(
            "Find nearby pharmacies within about 2 km of the Colosseum in Rome. "
            "Return names and distances as text."
        ),
        active_state=_state(),
    )

    assert decision.status in {"accepted", "discovery_required"}
    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert CapabilityDomain.DATA_RETRIEVAL in decision.route.secondary_domains
    assert CapabilityDomain.MAP_RENDERING not in decision.route.secondary_domains
    assert "data_bearing_place_search_route_normalized" in decision.reason_codes


###############################################################################
def test_router_keeps_text_only_coordinate_lookup_free_of_provider_data() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            presentation="text",
            operation="retrieve",
            capability_queries=["coordinates"],
        ),
        user_message=(
            "What are the coordinates of the Colosseum in Rome? Give latitude "
            "and longitude as text only; don't load a map."
        ),
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "resolve_location"
    assert decision.route.capability_queries == []
    assert decision.route.requires_location is True
    assert decision.capability_ids == []
    assert "text_only_coordinate_lookup_route_normalized" in decision.reason_codes


###############################################################################
def test_router_normalizes_saved_evidence_inspection_without_provider_lookup() -> None:
    state = _state()
    state.evidence_refs = ["evidence-previous"]
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            presentation="text",
            operation="retrieve",
            requires_location=True,
            capability_queries=["pharmacy near the Colosseum"],
            target_refs=["Colosseum", "pharmacies"],
            filters={"category": "pharmacy"},
        ),
        user_message=(
            "Inspect the evidence from the immediately preceding pharmacy lookup. "
            "Use saved results only and do not fetch again or render a map."
        ),
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "inspect_evidence"
    assert decision.route.capability_queries == []
    assert decision.route.explicit_capability_ids == []
    assert decision.route.requires_location is False
    assert decision.route.spatial_scope is None
    assert decision.route.target_refs == []
    assert decision.route.filters == {}
    assert decision.capability_ids == []
    assert "text_evidence_inspection_route_normalized" in decision.reason_codes


###############################################################################
def test_router_does_not_assume_evidence_exists_in_a_new_conversation() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            presentation="text",
            operation="retrieve",
            capability_queries=["evidence from the previous pharmacy lookup"],
        ),
        user_message="Inspect evidence from the previous pharmacy lookup.",
        active_state=_state(),
    )

    assert decision.route.operation == "retrieve"
    assert "text_evidence_inspection_route_normalized" not in decision.reason_codes


def test_router_normalizes_geocoding_route_for_location_only_map() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            operation="resolve_place",
            capability_queries=[
                "place search",
                "geocoding",
                "reverse geocoding",
            ],
        ),
        user_message="35.6762, 139.6503",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert decision.route.secondary_domains == []
    assert decision.route.operation == "show_location_on_map"
    assert decision.route.capability_queries == ["place search", "map viewport"]
    assert "location_map_route_normalized" in decision.reason_codes


###############################################################################
def test_router_normalizes_named_landmark_map_route() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            operation="show_on_map",
            capability_queries=[
                "place search",
                "landmark lookup",
                "map view of a named feature",
            ],
        ),
        user_message="Show Table Mountain near Cape Town, South Africa on the map.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.MAP_RENDERING
    assert decision.route.operation == "show_location_on_map"
    assert decision.route.capability_queries == ["place search", "map viewport"]
    assert "location_map_route_normalized" in decision.reason_codes


###############################################################################
def test_router_preserves_explicit_poi_landmark_lookup() -> None:
    decision = _router().validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            operation="locate",
            capability_queries=["place search", "poi"],
        ),
        user_message="Locate the Acropolis Museum in Athens, Greece.",
        active_state=_state(),
    )

    assert decision.route.primary_domain is CapabilityDomain.PLACE_SEARCH
    assert decision.route.operation == "locate"
    assert decision.route.capability_queries == ["place search", "poi"]
    assert "location_map_route_normalized" not in decision.reason_codes

###############################################################################
def test_router_normalizes_undated_recent_historical_scope_to_current() -> None:
    decision = _router().validate_route(
        _route(
            temporal_scope={"mode": "historical", "granularity": "recent"}
        ),
        user_message="Show recent traffic in Zurich.",
        active_state=_state(),
    )

    assert decision.status == "accepted"
    assert decision.route.temporal_scope.mode == "current"
    assert "recent_scope_normalized_to_current" in decision.reason_codes

###############################################################################
def test_router_preserves_dated_historical_scope() -> None:
    decision = _router().validate_route(
        _route(
            temporal_scope={
                "mode": "historical",
                "granularity": "day",
                "start_time_iso": "2026-09-01T00:00:00Z",
                "end_time_iso": "2026-09-02T00:00:00Z",
            }
        ),
        user_message="Show traffic from September 1.",
        active_state=_state(),
    )

    assert decision.status == "discovery_required"
    assert decision.route.temporal_scope.mode == "historical"
    assert "recent_scope_normalized_to_current" not in decision.reason_codes
