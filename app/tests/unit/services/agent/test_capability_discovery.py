from __future__ import annotations

from typing import Any, cast

import pytest

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import AgentPhase, AgentRunState, CapabilityRoute
from server.services.agent.capability_router import CapabilityRouter
from server.services.geospatial.capability_registry import CapabilityRegistry

REGISTRY = CapabilityRegistry()


###############################################################################
class _Runtime:

    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def access_available(self, capability_id: str) -> bool:
        return True

    # -------------------------------------------------------------------------
    def supports_mode(self, capability_id: str, mode: str) -> bool:
        return True


###############################################################################
def _declaring(variable: str) -> list[str]:
    snapshot = REGISTRY.snapshot
    return [
        str(item["id"])
        for item in (*snapshot.overlays, *snapshot.tools)
        if variable in cast(dict[str, list[str]], item.get("metadata", {})).get("variables", [])
    ]


###############################################################################
def _shortlist(queries: list[str], **constraints: Any) -> list[str]:
    domains = constraints.pop("domains", {CapabilityDomain.DATA_RETRIEVAL})
    found = REGISTRY.shortlist(
        domains=domains,
        queries=queries,
        explicit_ids=[],
        runtime_registry=_Runtime(),
        limit=50,
        **constraints,
    )
    return [str(item["id"]) for item in found]


###############################################################################
def _state() -> AgentRunState:
    return AgentRunState(
        request_id="request-1",
        conversation_id="conversation-1",
        phase=AgentPhase.ROUTE_REQUEST,
        user_message="",
    )


###############################################################################
def _route(**overrides: Any) -> CapabilityRoute:
    values: dict[str, Any] = {
        "primary_domain": CapabilityDomain.DATA_RETRIEVAL,
        "task_mode": "execute",
        "presentation": "map",
        "location_mode": "target",
    }
    values.update(overrides)
    return CapabilityRoute.model_validate(values)


###############################################################################
@pytest.mark.parametrize(
    "variable, spellings",
    [
        ("maximum temperature", ["maximum temperature", "max temperature", "highest temperature"]),
        ("minimum temperature", ["minimum temperature", "min temperature", "lowest temperature"]),
        ("cloud cover", ["cloud cover"]),
    ],
)
def test_declared_variable_is_found_whatever_the_spelling(
    variable: str, spellings: list[str]
) -> None:
    declared = _declaring(variable)
    assert declared
    for spelling in spellings:
        found = _shortlist(
            [f"forecast {spelling}", spelling],
            temporal_mode="forecast",
            temporal_granularity="day",
            has_explicit_time_range=True,
        )
        assert set(declared) <= set(found), spelling


###############################################################################
def test_time_enabled_gibs_layers_serve_dated_requests_and_others_do_not() -> None:
    layers = [
        item
        for item in REGISTRY.snapshot.overlays
        if item.get("provider") == "gibs"
    ]
    dated = {
        str(item["id"])
        for item in layers
        if "historical" in item["executionContract"]["temporal_modes"]
    }
    assert dated
    found = set(
        _shortlist(
            ["NASA GIBS imagery"],
            domains={CapabilityDomain.DATA_RETRIEVAL, CapabilityDomain.MAP_RENDERING},
            temporal_mode="historical",
            temporal_granularity="day",
            has_explicit_time_range=True,
            requires_render=True,
        )
    )
    assert found == dated
    assert {str(item["id"]) for item in layers} - dated


###############################################################################
def test_catalog_layer_name_is_a_capability_reference_not_a_place() -> None:
    layer = next(
        item
        for item in REGISTRY.snapshot.overlays
        if item.get("provider") == "gibs"
        and "historical" in item["executionContract"]["temporal_modes"]
    )
    router = CapabilityRouter(capability_registry=REGISTRY, runtime_registry=cast(Any, _Runtime()))
    decision = router.validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            secondary_domains=[CapabilityDomain.MAP_RENDERING],
            operation="show",
            target_refs=[str(layer["name"]), "Africa"],
        ),
        user_message="Show the layer.",
        active_state=_state(),
    )

    assert decision.route.target_refs == ["Africa"]
    assert decision.route.capability_queries == [str(layer["name"])]
    assert decision.route.primary_domain is CapabilityDomain.DATA_RETRIEVAL
    assert "catalog_reference_not_a_place" in decision.reason_codes


###############################################################################
def test_place_names_are_never_taken_for_catalog_references() -> None:
    router = CapabilityRouter(capability_registry=REGISTRY, runtime_registry=cast(Any, _Runtime()))
    decision = router.validate_route(
        _route(
            primary_domain=CapabilityDomain.PLACE_SEARCH,
            target_refs=["Zurich", "New York", "Land of Fire"],
        ),
        user_message="Show Zurich.",
        active_state=_state(),
    )

    assert decision.route.target_refs == ["Zurich", "New York", "Land of Fire"]
    assert "catalog_reference_not_a_place" not in decision.reason_codes


###############################################################################
def test_question_about_retrieved_evidence_is_routed_to_evidence_inspection() -> None:
    state = _state()
    state.evidence_refs = ["evidence-previous"]
    router = CapabilityRouter(capability_registry=REGISTRY, runtime_registry=cast(Any, _Runtime()))
    decision = router.validate_route(
        _route(
            presentation="text",
            operation="inspect_evidence",
            target_refs=["Japan"],
            capability_queries=["earthquake"],
        ),
        user_message="Which one of those is the strongest, and where exactly is it?",
        active_state=state,
    )

    assert decision.status == "accepted"
    assert decision.capability_ids == []
    assert decision.route.capability_queries == []
    assert decision.route.target_refs == []
    assert decision.route.location_mode == "none"


###############################################################################
def test_evidence_inspection_without_prior_evidence_asks_instead_of_searching() -> None:
    router = CapabilityRouter(capability_registry=REGISTRY, runtime_registry=cast(Any, _Runtime()))
    decision = router.validate_route(
        _route(presentation="text", operation="inspect_evidence", location_mode="none"),
        user_message="Which one of those is the strongest?",
        active_state=_state(),
    )

    assert decision.status == "clarification"
    assert "no_evidence_to_inspect" in decision.reason_codes


###############################################################################
def test_declared_semantic_alias_and_spelling_variant_find_the_capability() -> None:
    aliased = {
        str(item["id"]): cast(dict[str, list[str]], item["metadata"])["semantic_aliases"]
        for item in REGISTRY.snapshot.overlays
        if cast(dict[str, list[str]], item.get("metadata", {})).get("semantic_aliases")
    }
    assert aliased
    for capability_id, aliases in aliased.items():
        for alias in aliases:
            assert capability_id in _shortlist([alias.replace("colour", "color"), alias])


###############################################################################
def test_reading_provider_records_as_text_is_not_filtered_by_the_inspect_label() -> None:
    searchable = {
        str(item["id"])
        for item in REGISTRY.snapshot.overlays
        if "search" in cast(dict[str, list[str]], item["executionContract"])["supported_operations"]
        and "inspect" not in cast(dict[str, list[str]], item["executionContract"])["supported_operations"]
    }
    assert searchable
    for capability_id in searchable:
        assert capability_id in _shortlist([capability_id], operation="inspect")


###############################################################################
@pytest.mark.parametrize("query", ["air quality measurements", "air quality"])
def test_air_quality_is_discoverable_around_a_place_whatever_the_wording(query: str) -> None:
    candidates = REGISTRY.shortlist(
        domains={CapabilityDomain.MIXED}, queries=[query], explicit_ids=[], runtime_registry=cast(Any, _Runtime()),
        limit=50, scope_kind="radius",
    )

    assert "openmeteo_air_quality_forecast" in {item["id"] for item in candidates}


###############################################################################
def test_a_paraphrase_no_capability_names_is_not_an_obligation() -> None:
    assert REGISTRY.servable_queries(["cloud cover forecast", "sky clarity astronomical viewing conditions"]) == ["cloud cover forecast"]


###############################################################################
def test_shortlist_descriptors_carry_a_bounded_reason() -> None:
    from server.services.agent.tool_handlers.catalog import _descriptor

    item = next(iter(REGISTRY.snapshot.overlays))
    keyword = str(cast(dict[str, list[str]], item["metadata"])["keywords"][0])

    matched = _descriptor(REGISTRY, cast(Any, _Runtime()), item, [keyword])
    unmatched = _descriptor(REGISTRY, cast(Any, _Runtime()), item, ["zzzz"])

    assert keyword.split()[0].casefold() in matched["reason"]
    assert unmatched["reason"].startswith("domain ")
    assert len(matched["reason"]) <= 120
