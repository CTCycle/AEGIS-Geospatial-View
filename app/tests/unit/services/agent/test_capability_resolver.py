from __future__ import annotations


import pytest

from server.contracts.extraction import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedAction,
    OverlayCommand,
    OverlaySelector,
    OverlayScope,
    TemporalSignal,
    TurnParseResult,
)
from server.services.agent.capability_resolver import CapabilityResolver
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def _turn(
    text: str,
    layer: str,
    *,
    temporal_mode: str = "none",
    temporal_granularity: str = "none",
    temporal_aggregation: str = "none",
    atomic_layers: list[str] | None = None,
) -> TurnParseResult:
    return TurnParseResult(
        user_text=text,
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="data_layer_query",
            action_label="Layer query",
            requested_visualizations=[layer],
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(
            mode=temporal_mode,
            granularity=temporal_granularity,
            aggregation=temporal_aggregation,
        ),
        parser_confidence=0.9,
        requested_layers=[layer],
        atomic_tasks=(
            [{"required_layers": atomic_layers}] if atomic_layers is not None else []
        ),
        tools_needed=True,
    )


###############################################################################
class _Credentials:
    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN001
        _ = provider, label
        return None


###############################################################################
def _runtime() -> RuntimeRegistry:
    return RuntimeRegistry(
        manifest_loader=GeospatialManifestLoader(),
        credentials_repo=_Credentials(),  # type: ignore[arg-type]
    )


###############################################################################
def _resolver() -> CapabilityResolver:
    return CapabilityResolver(
        capability_registry=CapabilityRegistry(),
        runtime_registry=_runtime(),
    )


###############################################################################
def test_preserves_enabled_exact_capability_id() -> None:
    resolved = _resolver().resolve(
        _turn("Show precipitation rate", "IMERG_Precipitation_Rate")
    )
    assert resolved.requested_layers == ["IMERG_Precipitation_Rate"]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_precipitation_radar_semantics() -> None:
    resolved = _resolver().resolve(
        _turn("Show current rain radar over Paris", "rain radar")
    )
    assert resolved.requested_layers == ["rainviewer_precipitation_radar"]


###############################################################################
def test_resolves_precipitation_rate_semantics() -> None:
    resolved = _resolver().resolve(
        _turn("Show precipitation intensity over Paris", "precipitation rate")
    )
    assert resolved.requested_layers == ["IMERG_Precipitation_Rate"]


###############################################################################
def test_resolves_forecast_semantics() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show the rain forecast over Paris",
            "openmeteo_weather_forecast",
            temporal_mode="forecast",
        )
    )
    assert resolved.requested_layers == ["openmeteo_weather_forecast"]


###############################################################################
def test_preserves_canonical_capability_ids_inside_overlay_commands() -> None:
    turn = _turn("Show weather over Zurich", "openmeteo_weather_forecast")
    turn = turn.model_copy(
        update={
            "overlay_commands": [
                OverlayCommand(
                    action="add",
                    selector=OverlaySelector(
                        capability_ids=["openmeteo_weather_forecast"]
                    ),
                )
            ]
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.overlay_commands[0].selector.capability_ids == [
        "openmeteo_weather_forecast"
    ]


###############################################################################
def test_preserves_unmatched_capability_ids_for_focused_clarification() -> None:
    turn = _turn("Hide the fictional overlay", "fictional")
    turn = turn.model_copy(
        update={
            "overlay_commands": [
                OverlayCommand(
                    action="hide",
                    selector=OverlaySelector(capability_ids=["fictional_overlay"]),
                )
            ]
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.overlay_commands[0].selector.capability_ids == ["fictional_overlay"]


###############################################################################
def test_unsupported_direct_values_preserve_valid_overlay_mutation() -> None:
    turn = _turn(
        "Remove visible overlays and show average house prices",
        "house_prices",
    )
    turn = turn.model_copy(
        update={
            "task_class": "direct_query",
            "requested_layers": [],
            "requested_concepts": ["house_prices"],
            "overlay_commands": [
                OverlayCommand(
                    action="remove",
                    selector=OverlaySelector(visibility="visible"),
                    scope=OverlayScope(kind="current_view"),
                )
            ],
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == []
    assert resolved.overlay_commands[0].action == "remove"
    assert resolved.overlay_commands[0].scope.kind == "current_view"
    assert resolved.overlay_commands[0].selector.visibility == "visible"
    assert resolved.clarification_plan is not None
    assert resolved.clarification_plan["blocking_fields"] == ["direct_data_source"]
    assert resolved.clarification_plan["apply_visualization_changes"] is True
    assert "executable values" in resolved.clarification_plan["question"]
    assert "unsupported" in resolved.clarification_plan["question"]
    assert any("house_prices" in item for item in resolved.capability_limitations)


###############################################################################
def test_resolves_air_quality_underscore_semantics_to_enabled_capability() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show air quality forecast overlay for Paris",
            "openmeteo_air_quality_forecast",
        )
    )
    assert resolved.requested_layers == ["openmeteo_air_quality_forecast"]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_all_supported_atomic_task_layers() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show air quality and weather around Zurich",
            "openmeteo_air_quality_forecast",
            atomic_layers=[
                "openmeteo_air_quality_forecast",
                "openmeteo_weather_forecast",
            ],
        )
    )

    assert resolved.requested_layers == [
        "openmeteo_air_quality_forecast",
        "openmeteo_weather_forecast",
    ]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_generic_poi_transit_and_radar_atomic_layers() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show restaurants, transit stops, and precipitation radar around Rome",
            "overpass_poi_amenities",
            atomic_layers=[
                "overpass_poi_amenities",
                "gtfs_static",
                "rainviewer_precipitation_radar",
            ],
        )
    )

    assert resolved.requested_layers == [
        "overpass_poi_amenities",
        "gtfs_static",
        "rainviewer_precipitation_radar",
    ]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_poi_category_as_refinement_of_generic_poi_capability() -> None:
    turn = _turn("Find hospitals around Rome", "hospitals")
    turn = turn.model_copy(
        update={
            "requested_layers": [],
            "requested_concepts": ["hospitals"],
            "poi_categories": ["hospitals"],
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == ["overpass_poi_amenities"]
    assert resolved.poi_categories == ["hospitals"]
    assert resolved.capability_limitations == []
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_traffic_semantics_to_enabled_capability() -> None:
    resolved = _resolver().resolve(
        _turn("Show traffic flow around the Colosseum in Rome", "tomtom_traffic_flow")
    )
    assert resolved.requested_layers == ["tomtom_traffic_flow"]
    assert resolved.clarification_plan is None


###############################################################################
def test_unsupported_historical_aggregation_is_reported_without_date_special_cases() -> (
    None
):
    resolved = _resolver().resolve(
        _turn(
            "Can you now show Tour Eiffel area with rain level in October (mean value)",
            "openmeteo_weather_forecast",
            temporal_mode="historical",
            temporal_granularity="month",
            temporal_aggregation="mean",
        )
    )
    assert resolved.requested_layers == []
    assert resolved.clarification_plan is not None
    assert "October" not in resolved.clarification_plan["question"]
    assert "structured layer request" in resolved.clarification_plan["reason"]
    assert "unresolved_geospatial_capability" in resolved.ambiguities


###############################################################################
class _DisabledRuntimeRegistry:
    # -------------------------------------------------------------------------
    def is_enabled(self, capability_id: str) -> bool:
        return capability_id != "IMERG_Precipitation_Rate"


###############################################################################
def test_disabled_exact_capability_is_not_planned() -> None:
    resolver = CapabilityResolver(
        capability_registry=CapabilityRegistry(),
        runtime_registry=_DisabledRuntimeRegistry(),
    )
    resolved = resolver.resolve(
        _turn("Show precipitation rate", "IMERG_Precipitation_Rate")
    )
    assert resolved.requested_layers == []
    assert resolved.clarification_plan is not None


###############################################################################
def test_unmatched_semantic_layer_returns_clarification() -> None:
    resolved = _resolver().resolve(
        _turn("Show a completely fictional atmospheric index", "fictional")
    )
    assert resolved.requested_layers == []
    assert resolved.clarification_plan is not None
    assert "unresolved_geospatial_capability" in resolved.ambiguities


###############################################################################
def test_unknown_underscore_identifier_is_not_treated_as_resolved() -> None:
    resolved = _resolver().resolve(
        _turn("Show a fake Overpass layer", "overpass_fake_layer")
    )
    assert resolved.requested_layers == []
    assert resolved.clarification_plan is not None


###############################################################################
def test_resolves_semantic_direct_request_to_direct_tool_capability() -> None:
    turn = _turn("What is the weather in Rome?", "")
    turn = turn.model_copy(
        update={
            "task_class": "direct_query",
            "requested_layers": [],
            "requested_concepts": ["weather"],
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == ["get_weather_forecast"]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_gbif_occurrence_capability() -> None:
    resolved = _resolver().resolve(
        _turn("Show species observations around Zurich", "gbif_species_occurrences")
    )

    assert resolved.requested_layers == ["gbif_species_occurrences"]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_openmeteo_elevation_after_explicit_usage_opt_in(monkeypatch) -> None:
    monkeypatch.setenv("AEGIS_ALLOW_RESTRICTED_SOURCES", "true")
    resolved = _resolver().resolve(
        _turn("Show point elevation around Zurich", "openmeteo_elevation")
    )

    assert resolved.requested_layers == ["openmeteo_elevation"]
    assert resolved.clarification_plan is None


###############################################################################
def test_resolves_humidity_direct_request_to_weather_tool() -> None:
    turn = _turn("What is the humidity in Sanremo?", "")
    turn = turn.model_copy(
        update={
            "task_class": "direct_query",
            "requested_layers": [],
            "requested_concepts": ["humidity"],
            "requested_attributes": ["humidity"],
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == ["get_weather_forecast"]
    assert resolved.clarification_plan is None


###############################################################################
def test_ignores_presentation_action_tags_as_dataset_concepts() -> None:
    turn = _turn("Show Springfield", "")
    turn = turn.model_copy(
        update={
            "requested_layers": [],
            "requested_concepts": [],
            "normalized_action": NormalizedAction(
                action_id="data_layer_query",
                action_label="Layer query",
                action_tags=["show"],
                requested_visualizations=[],
                requires_location=True,
            ),
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == []
    assert resolved.capability_limitations == []
    assert resolved.clarification_plan is None


@pytest.mark.parametrize(
    "action_tag", ["show_map", "map_center", "navigate", "relocate"]
)
def test_ignores_structured_map_interaction_tags_as_dataset_concepts(
    action_tag: str,
) -> None:
    turn = _turn("Show a location", "")
    turn = turn.model_copy(
        update={
            "location_signals": [LocationSignal(signal_type="city", raw_value="Rome")],
            "normalized_action": NormalizedAction(
                action_id="map_search",
                action_label="Location map",
                action_tags=[action_tag],
                requires_location=True,
            ),
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == []
    assert resolved.capability_limitations == []
    assert resolved.clarification_plan is None


###############################################################################
def test_location_focus_drops_catalog_keyword_layers_without_typed_data_request() -> (
    None
):
    turn = _turn("Map the agency site", "esa_worldcover").model_copy(
        update={
            "location_signals": [
                LocationSignal(signal_type="poi", raw_value="agency site"),
                LocationSignal(signal_type="city", raw_value="Noordwijk"),
            ],
            "entity_target": "agency site",
            "map_target": "agency site in Noordwijk",
            "normalized_action": NormalizedAction(
                action_id="geospatial_data_retrieval",
                action_label="Map the agency site",
                task_tags=["map", "poi"],
                action_tags=["map", "location"],
                requires_location=True,
            ),
            "atomic_tasks": [
                {"task_type": "geocode", "required_layers": []},
                {"task_type": "map_render", "required_layers": []},
            ],
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == []
    assert resolved.clarification_plan is None


###############################################################################
def test_retains_semantic_action_tags_for_catalog_resolution() -> None:
    turn = _turn("Show weather in Rome", "")
    turn = turn.model_copy(
        update={
            "requested_layers": [],
            "requested_concepts": [],
            "normalized_action": NormalizedAction(
                action_id="data_layer_query",
                action_label="Layer query",
                action_tags=["weather"],
                requested_visualizations=[],
                requires_location=True,
            ),
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.requested_layers == ["openmeteo_weather_forecast"]
    assert resolved.clarification_plan is None


def test_explicit_boundary_concept_is_not_location_only() -> None:
    turn = _turn(
        "Show the geographic boundary of Canton Ticino.", "boundary"
    ).model_copy(
        update={
            "requested_layers": [],
            "requested_concepts": ["boundary"],
            "map_target": "Ticino",
            "atomic_tasks": [],
        }
    )
    turn.normalized_action.action_id = "geospatial_data_retrieval"
    assert not CapabilityResolver.is_location_focus_only(turn, [])


def test_district_concept_remains_location_navigation() -> None:
    turn = _turn("Show EUR district in Rome", "district").model_copy(update={
        "requested_layers": [], "requested_concepts": ["district"],
        "map_target": "EUR, Rome", "atomic_tasks": [],
    })
    turn.normalized_action.action_id = "geospatial_data_retrieval"
    assert CapabilityResolver.is_location_focus_only(turn, [])
