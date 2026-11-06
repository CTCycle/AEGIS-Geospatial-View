from __future__ import annotations
import asyncio
import pytest
from typing import Any
from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentGoal, CapabilityRoute, AgentPhase, AgentRunState, derive_request_obligations
from server.domain.agent.decision import ResolvedLocation, ClarificationRequest
from server.services.agent.tool_definitions import CapabilityDiscoveryInput, ResolveLocationInput
from server.services.agent.tool_handlers.catalog import CatalogToolHandler
from server.services.geospatial.capability_registry import CapabilityRegistry
from pydantic import ValidationError
from server.services.agent.location_resolver import NO_CANDIDATE_REASON, LocationResolver
from server.services.agent.tool_handlers.location import LocationToolHandler
from server.services.agent.completion import build_completion_summary
from server.services.agent.final_answer_check import check_final_answer

# --- test_catalog_tool_handler.py ---



###############################################################################
class _CapabilityRegistry:

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.last_shortlist_kwargs: dict[str, Any] = {}
        self.items = [
            {"id": "first", "name": "First", "provider": "test"},
            {"id": "second", "name": "Second", "provider": "test"},
        ]

    # -------------------------------------------------------------------------
    def shortlist(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.last_shortlist_kwargs = kwargs
        return self.items

    # -------------------------------------------------------------------------
    def execution_contract(self, capability_id: str) -> dict[str, Any]:
        return {"capability_id": capability_id, "render_support": "vector"}

###############################################################################
class _RuntimeRegistry:

    # -------------------------------------------------------------------------
    def is_enabled(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, _capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def supports_mode(self, _capability_id: str, _mode: str) -> bool:
        return True

###############################################################################
def test_discovery_cursor_returns_a_stable_bounded_page() -> None:
    handler = CatalogToolHandler(
        capability_registry=_CapabilityRegistry(),  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="find capabilities",
    )

    result = asyncio.run(
        handler.discover(
            CapabilityDiscoveryInput(cursor="1", limit=1),
            state,
        )
    )

    assert result.status == "success"
    assert result.data == {
        "capabilities": [
                {
                    "id": "second",
                    "name": "Second",
                    "summary": "",
                    "provider": "test",
                    "operations": [],
                    "render_support": "vector",
                    "reason": "",
                }
        ],
        "provider_id": None,
        "next_cursor": None,
        "total": 2,
    }

###############################################################################
def test_catalog_inventory_does_not_apply_execution_operation_or_point_scope() -> None:
    registry = _CapabilityRegistry()
    handler = CatalogToolHandler(
        capability_registry=registry,  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-inventory",
        conversation_id="conversation-inventory",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="What map data can you show for Florence, Italy?",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            secondary_domains=[
                CapabilityDomain.PLACE_SEARCH,
                CapabilityDomain.MAP_RENDERING,
            ],
            task_mode="execute",
            presentation="text",
            location_mode="target",
            capability_queries=[],
            operation="discover_available_map_data",
            target_refs=["Florence, Italy"],
            spatial_scope={"kind": "point", "target_refs": ["Florence, Italy"]},
        ),
    )

    result = asyncio.run(
        handler.discover(
            CapabilityDiscoveryInput(query="map data capabilities", limit=12),
            state,
        )
    )

    assert result.status == "success"
    assert registry.last_shortlist_kwargs["queries"] == []
    assert registry.last_shortlist_kwargs["operation"] is None
    assert registry.last_shortlist_kwargs["scope_kind"] is None
    assert registry.last_shortlist_kwargs["domains"] == {CapabilityDomain.MIXED}

###############################################################################
def test_catalog_inventory_page_matches_model_observation_limit() -> None:
    registry = _CapabilityRegistry()
    registry.items = [
        {"id": f"capability-{index}", "name": f"Capability {index}", "provider": "test"}
        for index in range(15)
    ]
    handler = CatalogToolHandler(
        capability_registry=registry,  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-paged-inventory",
        conversation_id="conversation-paged-inventory",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="List the available map data capabilities.",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.PROVIDER_DISCOVERY,
            task_mode="execute",
            presentation="text",
            location_mode="none",
            operation="discover_available_map_data",
        ),
    )

    result = asyncio.run(
        handler.discover(CapabilityDiscoveryInput(limit=50), state)
    )

    assert result.status == "success"
    assert len(result.data["capabilities"]) == 12  # type: ignore[index]
    assert result.data["next_cursor"] == "12"  # type: ignore[index]
    assert result.data["total"] == 15  # type: ignore[index]

###############################################################################
@pytest.mark.parametrize(
    ("kind", "target", "key", "label"),
    [
        ("point", "Rome, Italy", "rome, italy", "Rome, Italy"),
        ("viewport", "current map view", "current_map_view", "Current map view"),
    ],
)
def test_point_location_is_lowered_to_provider_bbox_for_execution_discovery(
    kind: str, target: str, key: str, label: str
) -> None:
    registry = _CapabilityRegistry()
    handler = CatalogToolHandler(
        capability_registry=registry,  # type: ignore[arg-type]
        runtime_registry=_RuntimeRegistry(),  # type: ignore[arg-type]
    )
    state = AgentRunState(
        request_id="request-point-discovery",
        conversation_id="conversation-point-discovery",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show aerosol over Rome.",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.MAP_RENDERING,
            secondary_domains=[CapabilityDomain.DATA_RETRIEVAL],
            task_mode="execute",
            presentation="map",
            location_mode="target",
            capability_queries=["aerosol"],
            operation="render_layer",
            target_refs=[target],
            spatial_scope={"kind": kind, "target_refs": [target]},
        ),
    )
    state.location_refs[key] = ResolvedLocation(
        label=label,
        latitude=41.89,
        longitude=12.48,
        bbox=[12.2, 41.6, 12.9, 42.2],
        country="Italy",
    )

    asyncio.run(handler.discover(CapabilityDiscoveryInput(query="aerosol"), state))

    assert registry.last_shortlist_kwargs["scope_kind"] == "bbox"

# --- test_location_tool_handler.py ---



###############################################################################
@pytest.mark.asyncio
async def test_coordinate_query_is_resolved_without_geocoder_egress() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show 46.0037, 8.9511.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(
            query="46.0037, 8.9511",
            expected_location_type="coordinates",
        ),
        state,
    )

    assert result.status == "success"
    location = state.location_refs["46.0037, 8.9511"]
    assert location.latitude == 46.0037
    assert location.longitude == 8.9511

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "address", [{"city": "Lugano", "county": "Lugano", "state": "Ticino", "country": "Switzerland"}, None]
)
async def test_coordinates_to_identify_are_reverse_geocoded_and_the_answer_must_name_them(
    address: dict[str, str] | None,
) -> None:
    # S15: "Show 46.0037, 8.9511 on the map and tell me what place that is."
    target = "46.0037, 8.9511"
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.MAP_RENDERING,
        task_mode="execute",
        presentation="both",
        location_mode="target",
        target_refs=[target],
    )
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show 46.0037, 8.9511 on the map and tell me what place that is.",
    )
    state.goal = AgentGoal(
        goal=state.user_message,
        task_mode="execute",
        presentation="both",
        operation="show",
        location_mode="target",
        target_ids=[target],
        obligations=derive_request_obligations(
            route,
            target_ids=[target],
            target_requirements=[],
            requirements=["location_resolved", "map_candidate_prepared"],
            data_variables=[],
        ),
    )

    ###############################################################################
    class ReverseGeocoder:

        # -------------------------------------------------------------------------
        def perform_reverse_request(self, _params: dict[str, str]) -> dict[str, Any] | None:
            return {"address": address} if address else None

    result = await LocationToolHandler(
        resolver=LocationResolver(nominatim_service=ReverseGeocoder())  # type: ignore[arg-type]
    ).resolve(ResolveLocationInput(query=target, expected_location_type="coordinates"), state)
    summary = build_completion_summary(state, {"location_resolved": True})
    identification = next(item for item in summary.obligations if item.kind == "identification")

    if address is None:
        assert result.summary == "Resolved 46.0037, 8.9511."
        assert identification.status == "unmet"
        assert "the name of the place at 46.0037, 8.9511" in summary.disclosure()
        return
    assert result.summary == "Resolved 46.0037, 8.9511: Lugano, Ticino, Switzerland."
    assert identification.status == "met"
    assert identification.values == ["Lugano, Ticino, Switzerland"]
    assert check_final_answer(
        "The map now shows 46.0037, 8.9511.",
        target_names=[target],
        required_targets=[identification.answer_must_name],
    ) == ["does not name the requested place 'Lugano'"]

###############################################################################
@pytest.mark.asyncio
async def test_invalid_coordinate_query_is_rejected_with_bounds() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Go to 91, 181.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(query="91, 181", expected_location_type="coordinates"),
        state,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_coordinates"
    assert result.data == {
        "resolution_status": "invalid_coordinates",
        "query": "91, 181",
        "latitude_bounds": [-90, 90],
        "longitude_bounds": [-180, 180],
    }

###############################################################################
@pytest.mark.asyncio
async def test_invalid_coordinates_in_user_text_override_context_target() -> None:
    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Go to 91, 181.",
    )

    result = await LocationToolHandler(resolver=LocationResolver()).resolve(
        ResolveLocationInput(query="Zurich", expected_location_type="city"),
        state,
    )

    assert result.status == "failed"
    assert result.error is not None
    assert result.error.code == "invalid_coordinates"
    assert result.data is not None
    assert result.data["query"] == "91, 181"

###############################################################################
@pytest.mark.asyncio
async def test_unresolved_target_id_is_resolved_as_initial_location_query() -> None:
    captured: list[tuple[str, str]] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            captured.append((signal.raw_value, signal.signal_type))
            return ResolvedLocation(
                label="Japan",
                latitude=36.2048,
                longitude=138.2529,
                source="geocoder",
            )

    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show me earthquakes around Japan.",
    )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(target_id="Japan", expected_location_type="country"),
        state,
    )

    assert result.status == "success"
    assert captured == [("Japan", "country")]
    assert state.location_refs["japan"].label == "Japan"

###############################################################################
class _TypedResolver:
    """Answer each signal type with a scripted geocoder outcome."""

    # -------------------------------------------------------------------------
    def __init__(self, outcomes: dict[str, ResolvedLocation | ClarificationRequest]) -> None:
        self.outcomes = outcomes
        self.types: list[str] = []

    # -------------------------------------------------------------------------
    async def resolve_location_signals(self, signals: Any, _memory: Any) -> Any:
        self.types.append(signals[0].signal_type)
        return self.outcomes[signals[0].signal_type]

_QUEENSLAND = ResolvedLocation(label="Colosseum, Queensland, Australia", latitude=-24.43, longitude=151.56,
                               source="geocoder", confidence=0.77)
_ROME_LANDMARK = ResolvedLocation(label="Colosseum, Rome, Italy", latitude=41.89, longitude=12.49,
                                  source="geocoder", confidence=0.87)

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expected_type", "landmark", "label", "types"),
    [
        # Untyped: a clearly more prominent landmark wins over the default settlement.
        (None, _ROME_LANDMARK, "Colosseum, Rome, Italy", ["city", "landmark"]),
        # Untyped: a city whose landmark lookup fails keeps the city.
        (None, ClarificationRequest(question="?", reason="none", missing_fields=["location"]),
         "Colosseum, Queensland, Australia", ["city", "landmark"]),
        # An explicit type is never second-guessed.
        ("city", _ROME_LANDMARK, "Colosseum, Queensland, Australia", ["city"]),
    ],
)
async def test_untyped_name_prefers_a_clearly_more_prominent_landmark(
    expected_type: str | None, landmark: Any, label: str, types: list[str]
) -> None:
    resolver = _TypedResolver({"city": _QUEENSLAND, "landmark": landmark})
    state = AgentRunState(request_id="request-1", conversation_id="conversation-1",
                          phase=AgentPhase.BUILD_TOOL_CONTEXT, user_message="Show the Colosseum")

    result = await LocationToolHandler(resolver=resolver).resolve(  # type: ignore[arg-type]
        ResolveLocationInput(query="Colosseum", target_id="Colosseum", expected_location_type=expected_type),
        state,
    )

    assert result.status == "success"
    assert state.location_refs["colosseum"].label == label
    assert resolver.types == types

###############################################################################
_ITALY = ResolvedLocation(label="Italy", latitude=42.6, longitude=12.6, source="geocoder", confidence=0.9)
_NO_CITY = ClarificationRequest(question="?", reason=NO_CANDIDATE_REASON, missing_fields=["location"])

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("city_outcome", "status", "types"),
    [
        # An untyped country never matches the "city" default; it resolves as a region.
        (_NO_CITY, "success", ["city", "administrative_geometry"]),
        # A genuine same-name ambiguity still asks instead of guessing another type.
        (ClarificationRequest(question="Which?", reason="Multiple candidates.", missing_fields=["location"]),
         "failed", ["city"]),
    ],
)
async def test_untyped_name_without_a_city_match_tries_a_region(
    city_outcome: ClarificationRequest, status: str, types: list[str]
) -> None:
    resolver = _TypedResolver({"city": city_outcome, "administrative_geometry": _ITALY})
    state = AgentRunState(request_id="request-1", conversation_id="conversation-1",
                          phase=AgentPhase.BUILD_TOOL_CONTEXT, user_message="Show earthquakes in Italy")

    result = await LocationToolHandler(resolver=resolver).resolve(  # type: ignore[arg-type]
        ResolveLocationInput(query="Italy", target_id="Italy"),
        state,
    )

    assert result.status == status
    assert resolver.types == types

###############################################################################
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "user_message", "expected"),
    [
        ("Florence, Tuscany, Italy", "Show me Florence.", "Florence"),
        ("Florence, Italy", "Show Florence, Italy.", "Florence, Italy"),
    ],
)
async def test_location_resolution_uses_only_user_stated_parent_qualifiers(
    query: str,
    user_message: str,
    expected: str,
) -> None:
    captured: list[str] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            captured.append(signals[0].raw_value)
            return ResolvedLocation(
                label="Florence, Tuscany, Italy",
                latitude=43.7698,
                longitude=11.2556,
                source="geocoder",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(query=query, expected_location_type="city"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message=user_message,
        ),
    )

    assert result.status == "success"
    assert captured == [expected]

###############################################################################
@pytest.mark.asyncio
async def test_ambiguous_location_is_a_typed_semantic_outcome() -> None:

    ###############################################################################
    class AmbiguousResolver(LocationResolver):

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, _signals, _memory):  # noqa: ANN001
            return ClarificationRequest(
                question="Which Springfield do you mean?",
                reason="Multiple candidates matched.",
                missing_fields=["location"],
            )

    result = await LocationToolHandler(resolver=AmbiguousResolver()).resolve(
        ResolveLocationInput(query="Springfield"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Show Springfield.",
        ),
    )

    assert result.status == "failed"
    assert result.semantic_outcome == "ambiguous"
    assert result.data == {
        "resolution_status": "ambiguous",
        "question": "Which Springfield do you mean?",
        "reason": "Multiple candidates matched.",
        "missing_fields": ["location"],
    }
    assert result.error is not None
    assert result.error.recovery == "request_user_input"

###############################################################################
@pytest.mark.asyncio
async def test_data_subject_is_rejected_as_a_place_without_geocoding() -> None:
    calls: list[object] = []

    ###############################################################################
    class CountingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            calls.append(signals)
            raise AssertionError("the subject word must not be geocoded")

    state = AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="Show earthquakes worldwide.",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            task_mode="execute",
            presentation="map",
            location_mode="search_area",
            capability_queries=["earthquakes"],
            target_refs=["World"],
        ),
    )

    result = await LocationToolHandler(resolver=CountingResolver()).resolve(  # type: ignore[arg-type]
        ResolveLocationInput(query="Earthquakes"), state
    )

    assert calls == []
    assert result.status == "failed"
    assert result.error is not None and result.error.code == "not_a_place"

###############################################################################
@pytest.mark.asyncio
async def test_administrative_geometry_type_reaches_the_native_resolver() -> None:
    captured: list[str] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            captured.append(signals[0].signal_type)
            return ResolvedLocation(
                label="Vermont, United States",
                latitude=44.0,
                longitude=-72.7,
                source="geocoder",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(
            query="Vermont, United States",
            expected_location_type="administrative_geometry",
        ),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Show a map of Vermont, United States.",
        ),
    )

    assert result.status == "success"
    assert captured == ["administrative_geometry"]

###############################################################################
@pytest.mark.asyncio
async def test_explicit_coordinates_in_clarification_text_override_unresolved_name() -> None:
    captured: list[tuple[str, float | None, float | None, str]] = []

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            captured.append(
                (signal.signal_type, signal.latitude, signal.longitude, signal.source)
            )
            return ResolvedLocation(
                label="45, -69",
                latitude=45.0,
                longitude=-69.0,
                source="text",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(
            query="Patagonia, Argentina",
            expected_location_type="region",
        ),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message=(
                "Use the broad region, centered approximately at 45.0, -69.0."
            ),
        ),
    )

    assert result.status == "success"
    assert captured == [("coordinates", 45.0, -69.0, "text")]

###############################################################################
@pytest.mark.asyncio
async def test_coordinate_text_supports_hemisphere_notation() -> None:

    ###############################################################################
    class CapturingResolver:

        # -------------------------------------------------------------------------
        async def resolve_location_signals(self, signals, _memory):  # noqa: ANN001
            signal = signals[0]
            return ResolvedLocation(
                label=signal.raw_value,
                latitude=signal.latitude or 0.0,
                longitude=signal.longitude or 0.0,
                source="text",
            )

    result = await LocationToolHandler(resolver=CapturingResolver()).resolve(
        ResolveLocationInput(query="Patagonia, Argentina", expected_location_type="region"),
        AgentRunState(
            request_id="request-1",
            conversation_id="conversation-1",
            phase=AgentPhase.BUILD_TOOL_CONTEXT,
            user_message="Center approximately at 45 degrees S, 69 degrees W.",
        ),
    )

    assert result.status == "success"
    assert result.data is not None
    assert result.data["coordinates"] == [-69.0, -45.0]

###############################################################################
def test_unknown_location_type_is_not_accepted_as_a_legacy_alias() -> None:
    with pytest.raises(ValidationError):
        ResolveLocationInput(
            query="Vermont, United States",
            expected_location_type="administrative_region",
        )


###############################################################################
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("quakes near Point Nemo from March 1 to March 7, 2024", None),
        ("storms on Sept. 9, 2023", None),
        ("show 41.9, 12.5 on 7, 2024 data", (41.9, 12.5)),
        ("show 41.9, 12.5", (41.9, 12.5)),
    ],
)
def test_text_coordinates_ignore_calendar_dates(text: str, expected) -> None:
    from server.services.agent.tool_handlers.location import (
        _parse_coordinate_pair_from_text,
        _search_text_coordinates,
    )

    assert _parse_coordinate_pair_from_text(text) == expected
    assert (_search_text_coordinates(text) is not None) is (expected is not None)
###############################################################################
class _KeylessRuntime(_RuntimeRegistry):

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return capability_id != "openchargemap_ev_charging"

###############################################################################
def test_empty_count_discovery_names_missing_credential_without_other_subjects() -> None:
    zurich = ResolvedLocation(
        label="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
        bbox=[8.45, 47.32, 8.62, 47.43],
        country="Switzerland",
    )
    state = AgentRunState(
        request_id="request-ev",
        conversation_id="conversation-ev",
        phase=AgentPhase.BUILD_TOOL_CONTEXT,
        user_message="How many EV charging stations are near Zurich?",
        route=CapabilityRoute(
            primary_domain=CapabilityDomain.DATA_RETRIEVAL,
            task_mode="execute",
            presentation="text",
            location_mode="target",
            capability_queries=["ev charging stations"],
            operation="count",
            target_refs=["Zurich"],
            spatial_scope={"kind": "point", "target_refs": ["Zurich"]},
        ),
        location_refs={"zurich": zurich},
    )
    handler = CatalogToolHandler(
        capability_registry=CapabilityRegistry(),
        runtime_registry=_KeylessRuntime(),  # type: ignore[arg-type]
    )

    result = asyncio.run(handler.discover(CapabilityDiscoveryInput(limit=12), state))

    data = result.data or {}
    assert result.status == "valid_empty"
    assert data["capabilities"] == []
    assert "openchargemap_ev_charging (missing a required credential)" in result.summary
    for alternatives in (
        item["alternatives"] for item in data["diagnostics"]["unmet_constraints"]
    ):
        assert all("charg" in str(item["id"]) for item in alternatives)
