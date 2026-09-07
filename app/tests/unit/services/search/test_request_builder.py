from __future__ import annotations

from server.domain.agent.decision import ResolvedLocation
from server.domain.agent.decision import ExecutionPlan
from server.domain.agent.interpretation import (
    CanonicalRequestInterpretation,
    CanonicalSpatialConstraint,
    CanonicalTarget,
    CanonicalTemporalConstraints,
)
from server.contracts.extraction import (
    ConversationContextSnapshot,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
    ViewportIntent,
)
from server.services.search.request_builder import RequestBuilder

###############################################################################
def test_request_builder_uses_wide_radius_for_city_level_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Berlin", latitude=52.5173885, longitude=13.3951309),
        NormalizedAction(
            action_id="show_city_map_berlin",
            action_label="Show city map Berlin",
            task_tags=["map", "city", "wide_view"],
            action_tags=["city_level"],
        ),
        viewport_intent=ViewportIntent(scope="city"),
    )

    assert viewport.radius_m == 18000.0

###############################################################################
def test_request_builder_uses_tighter_radius_for_exact_address_intent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="1600 Pennsylvania Avenue",
            latitude=38.8976387,
            longitude=-77.0365528,
            location_type="house",
            location_class="building",
            bbox=[-77.0370, 38.8972, -77.0362, 38.8980],
        ),
        NormalizedAction(
            action_id="show_exact_address_map",
            action_label="Show exact address map",
            task_tags=["map", "address"],
            action_tags=["exact_address"],
        ),
        viewport_intent=ViewportIntent(scope="street"),
    )

    assert viewport.radius_m <= 350.0
    assert viewport.bbox is not None

###############################################################################
def test_request_builder_prefers_explicit_viewport_intent_over_generic_defaults() -> (
    None
):
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(scope="street", reason="local_area_request"),
    )

    assert viewport.radius_m == 350.0

###############################################################################
def test_request_builder_tightens_relative_to_active_viewport() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(
            scope="street",
            tighten_relative_to_active=True,
            reason="explicit_tighter_view",
        ),
        active_visualization={
            "viewport": {
                "center_latitude": 44.4056,
                "center_longitude": 8.9463,
                "radius_m": 2500.0,
            }
        },
    )

    assert viewport.radius_m < 2500.0
    assert viewport.radius_m <= 875.0

###############################################################################
def test_request_builder_uses_geocoder_bbox_when_parser_intent_is_absent() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="Via Pisa, Genoa",
            latitude=44.4056,
            longitude=8.9463,
            location_type="road",
            location_class="highway",
            bbox=[8.9448, 44.4049, 8.9474, 44.4061],
        ),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
    )

    assert viewport.bbox is not None
    assert viewport.radius_m <= 400.0

###############################################################################
def test_request_builder_preserves_current_viewport_for_basemap_only_follow_up() -> (
    None
):
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(label="Genoa", latitude=44.4056, longitude=8.9463),
        NormalizedAction(
            action_id="map_search",
            action_label="General map request",
            task_tags=["map"],
            action_tags=[],
        ),
        viewport_intent=ViewportIntent(
            scope="preserve_current", reason="basemap_only_follow_up"
        ),
        active_visualization={
            "viewport": {
                "center_latitude": 44.4056,
                "center_longitude": 8.9463,
                "radius_m": 640.0,
                "bbox": [8.94, 44.40, 8.95, 44.41],
            }
        },
    )

    assert viewport.radius_m == 640.0
    assert viewport.bbox == [8.94, 44.4, 8.95, 44.41]

###############################################################################
def test_request_builder_recenters_when_follow_up_changes_location() -> None:
    builder = RequestBuilder()
    viewport = builder.build_viewport(
        ResolvedLocation(
            label="Zurich",
            latitude=47.3769,
            longitude=8.5417,
            location_type="city",
        ),
        NormalizedAction(
            action_id="map_search",
            action_label="Change map location",
            task_tags=["map"],
            action_tags=["correction"],
        ),
        viewport_intent=ViewportIntent(
            scope="preserve_current", reason="location_correction"
        ),
        active_visualization={
            "resolved_location": {
                "label": "Lugano",
                "latitude": 46.0037,
                "longitude": 8.9511,
            },
            "viewport": {
                "center_latitude": 46.0037,
                "center_longitude": 8.9511,
                "radius_m": 350.0,
            },
        },
    )

    assert viewport.center_latitude == 47.3769
    assert viewport.center_longitude == 8.5417
    assert viewport.radius_m == 18000.0


###############################################################################
def test_request_builder_preserves_temporal_mode_and_analysis_radius() -> None:
    builder = RequestBuilder()
    turn = TurnParseResult(
        user_text="Show historical earthquakes within 5 km of Zurich",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Earthquakes",
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(
            mode="historical",
            start_time_iso="2026-08-24T00:00:00+00:00",
            end_time_iso="2026-08-31T00:00:00+00:00",
        ),
        radius_m=5000.0,
        viewport_intent=ViewportIntent(scope="city"),
    )
    request = builder.build_location_search_request(
        ExecutionPlan(
            state="map_search",
            mode="map",
            action_id="geospatial_data_retrieval",
            overlay_ids=["usgs_earthquakes"],
        ),
        ResolvedLocation(
            label="Zurich",
            latitude=47.3769,
            longitude=8.5417,
            location_type="city",
        ),
        turn_contract=turn,
    )

    assert request.time_mode == "historical"
    assert request.start_time_iso == "2026-08-24T00:00:00+00:00"
    assert request.end_time_iso == "2026-08-31T00:00:00+00:00"
    assert request.analysis_radius_m == 5000.0
    assert request.viewport.radius_m >= 5000.0


###############################################################################
def test_request_builder_ignores_native_bbox_override_for_canonical_scope() -> None:
    builder = RequestBuilder()
    location = ResolvedLocation(
        label="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
        bbox=[8.3, 47.2, 8.7, 47.6],
    )
    canonical = CanonicalRequestInterpretation(
        request_id="canonical-bbox-1",
        primary_intent="geospatial_data_retrieval",
        targets=[
            CanonicalTarget(
                target_id="target-zurich",
                original_text="Zurich",
                entity_kind="city",
                resolved_location=location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="in",
                target_id="target-zurich",
                analysis_scope="bbox",
                provenance="explicit",
            )
        ],
    )
    stale_turn = TurnParseResult(
        user_text="Show current data elsewhere",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Data",
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        radius_m=900.0,
        poi_categories=["stale-category"],
    )
    request = builder.build_location_search_request(
        ExecutionPlan(
            state="map_search",
            mode="map",
            action_id="geospatial_data_retrieval",
            overlay_ids=["usgs_earthquakes"],
        ),
        location,
        turn_contract=stale_turn,
        canonical_request=canonical,
        target_id="target-zurich",
        canonical_arguments={"bbox": [0.0, 0.0, 1.0, 1.0]},
    )

    assert request.analysis_bbox == [8.3, 47.2, 8.7, 47.6]
    assert request.analysis_radius_m is None
    assert request.poi_categories == []


###############################################################################
def test_request_builder_uses_canonical_scope_and_time_over_stale_turn_fields() -> None:
    builder = RequestBuilder()
    location = ResolvedLocation(
        label="Zurich, Switzerland",
        latitude=47.3769,
        longitude=8.5417,
        location_type="city",
        bbox=[8.3, 47.2, 8.7, 47.6],
    )
    canonical = CanonicalRequestInterpretation(
        request_id="canonical-request-1",
        primary_intent="geospatial_data_retrieval",
        targets=[
            CanonicalTarget(
                target_id="target-zurich",
                original_text="Zurich",
                entity_kind="city",
                resolved_location=location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="within_distance",
                target_id="target-zurich",
                analysis_scope="radius",
                distance_m=5_000.0,
                provenance="explicit",
            )
        ],
        temporal_constraints=CanonicalTemporalConstraints(
            mode="historical",
            start_time_iso="2026-08-24T00:00:00+00:00",
            end_time_iso="2026-08-31T00:00:00+00:00",
        ),
    )
    stale_turn = TurnParseResult(
        user_text="Show current data elsewhere",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Data",
            requires_location=True,
        ),
        temporal_signal=TemporalSignal(mode="current"),
        radius_m=800.0,
    )

    request = builder.build_location_search_request(
        ExecutionPlan(
            state="map_search",
            mode="map",
            action_id="geospatial_data_retrieval",
            overlay_ids=["usgs_earthquakes"],
        ),
        location,
        turn_contract=stale_turn,
        canonical_request=canonical,
        target_id="target-zurich",
        canonical_arguments={
            "latitude": location.latitude,
            "longitude": location.longitude,
            # A model/native-tool argument must not override the canonical
            # radius compiled from the user's request.
            "radius_m": 900.0,
        },
    )

    assert request.analysis_scope == "radius"
    assert request.target_id == "target-zurich"
    assert request.analysis_radius_m == 5_000.0
    assert request.time_mode == "historical"
    assert request.start_time_iso == "2026-08-24T00:00:00+00:00"
    assert request.end_time_iso == "2026-08-31T00:00:00+00:00"

###############################################################################
def test_request_builder_uses_canonical_location_and_viewport_over_stale_turn() -> None:
    builder = RequestBuilder()
    canonical_location = ResolvedLocation(
        label="Rome, Italy",
        latitude=41.9028,
        longitude=12.4964,
        location_type="city",
        bbox=[12.3, 41.7, 12.7, 42.1],
    )
    stale_location = ResolvedLocation(
        label="London, United Kingdom",
        latitude=51.5074,
        longitude=-0.1278,
        location_type="city",
    )
    canonical = CanonicalRequestInterpretation(
        request_id="canonical-location-1",
        primary_intent="geospatial_data_retrieval",
        targets=[
            CanonicalTarget(
                target_id="target-rome",
                original_text="Rome",
                entity_kind="city",
                resolved_location=canonical_location,
                resolution_status="resolved",
            )
        ],
        spatial_constraints=[
            CanonicalSpatialConstraint(
                relationship="in",
                target_id="target-rome",
                analysis_scope="bbox",
                provenance="explicit",
            )
        ],
        presentation={
            "mode": "map",
            "viewport_operation": "city",
            "viewport_radius_m": 18_000.0,
        },
        map_required=True,
    )
    stale_turn = TurnParseResult(
        user_text="Show London at street scale",
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        normalized_action=NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Data",
            requires_location=True,
        ),
        location_signals=[],
        viewport_intent=ViewportIntent(scope="street", radius_hint_m=350.0),
    )
    request = builder.build_location_search_request(
        ExecutionPlan(
            state="map_search",
            mode="map",
            action_id="geospatial_data_retrieval",
            overlay_ids=["usgs_earthquakes"],
        ),
        stale_location,
        turn_contract=stale_turn,
        canonical_request=canonical,
        target_id="target-rome",
    )

    assert request.resolved_location.label == "Rome, Italy"
    assert request.viewport.center_latitude == canonical_location.latitude
    assert request.viewport.center_longitude == canonical_location.longitude
    assert request.viewport.radius_m == 18_000.0
