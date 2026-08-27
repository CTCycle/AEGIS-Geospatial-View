from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    NormalizedAction,
    OverlayCommand,
    OverlaySelector,
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
        temporal_signal=TemporalSignal(mode=temporal_mode),
        parser_confidence=0.9,
        requested_layers=[layer],
        atomic_tasks=(
            [{"required_layers": atomic_layers}]
            if atomic_layers is not None
            else []
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
        _turn("Show current rain radar over Paris", "precipitation")
    )
    assert resolved.requested_layers == ["rainviewer_precipitation_radar"]

###############################################################################
def test_resolves_precipitation_rate_semantics() -> None:
    resolved = _resolver().resolve(
        _turn("Show precipitation intensity over Paris", "precipitation")
    )
    assert resolved.requested_layers == ["IMERG_Precipitation_Rate"]

###############################################################################
def test_resolves_forecast_semantics() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show the rain forecast over Paris",
            "precipitation",
            temporal_mode="forecast",
        )
    )
    assert resolved.requested_layers == ["openmeteo_weather_forecast"]


def test_canonicalizes_alias_capability_ids_inside_overlay_commands() -> None:
    turn = _turn("Show weather over Zurich", "weather_forecast")
    turn = turn.model_copy(
        update={
            "overlay_commands": [
                OverlayCommand(
                    action="add",
                    selector=OverlaySelector(capability_ids=["weather_forecast"]),
                )
            ]
        }
    )

    resolved = _resolver().resolve(turn)

    assert resolved.overlay_commands[0].selector.capability_ids == [
        "openmeteo_weather_forecast"
    ]

###############################################################################
def test_resolves_air_quality_underscore_semantics_to_enabled_capability() -> None:
    resolved = _resolver().resolve(
        _turn("Show air quality overlay for Paris", "air_quality")
    )
    assert resolved.requested_layers == ["openmeteo_air_quality_forecast"]
    assert resolved.clarification_plan is None

###############################################################################
def test_resolves_all_supported_atomic_task_layers() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Show air quality and weather around Zurich",
            "openmeteo_air_quality_forecast",
            atomic_layers=["air_quality", "weather"],
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
            atomic_layers=["poi", "transit_stops", "precipitation_radar"],
        )
    )

    assert resolved.requested_layers == [
        "overpass_poi_amenities",
        "rainviewer_precipitation_radar",
    ]
    assert resolved.clarification_plan is None

###############################################################################
def test_resolves_traffic_semantics_to_enabled_capability() -> None:
    resolved = _resolver().resolve(
        _turn("Show traffic around the Colosseum in Rome", "traffic")
    )
    assert resolved.requested_layers == ["tomtom_traffic_flow"]
    assert resolved.clarification_plan is None

###############################################################################
def test_october_mean_returns_supported_alternatives_instead_of_invalid_id() -> None:
    resolved = _resolver().resolve(
        _turn(
            "Can you now show Tour Eiffel area with rain level in October (mean value)",
            "precipitation",
            temporal_mode="historical",
        )
    )
    assert resolved.requested_layers == []
    assert resolved.clarification_plan is not None
    assert "October mean" in resolved.clarification_plan["question"]
    assert "current precipitation radar" in resolved.clarification_plan["question"]
    assert "unsupported_historical_precipitation_mean" in resolved.ambiguities

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
