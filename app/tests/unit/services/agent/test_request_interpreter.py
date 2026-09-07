from __future__ import annotations

from server.contracts.extraction import (
    ConversationContextSnapshot,
    GeographicRelationship,
    LocationSignal,
    NormalizedAction,
    TemporalSignal,
    TurnParseResult,
)
from server.domain.agent.decision import ResolvedLocation
from server.services.agent.request_interpreter import RequestInterpreter


def _location(label: str, latitude: float, longitude: float) -> ResolvedLocation:
    return ResolvedLocation(
        label=label,
        latitude=latitude,
        longitude=longitude,
        location_type="city",
        confidence=0.99,
        bbox=[longitude - 0.1, latitude - 0.1, longitude + 0.1, latitude + 0.1],
    )


def _turn(**updates: object) -> TurnParseResult:
    payload: dict[str, object] = {
        "user_text": "Show earthquakes in Rome",
        "conversation_context": ConversationContextSnapshot(),
        "task_class": "map_search",
        "location_signals": [
            LocationSignal(
                signal_type="city",
                raw_value="Rome",
                normalized_value="Rome",
                confidence=0.98,
            )
        ],
        "normalized_action": NormalizedAction(
            action_id="geospatial_data_retrieval",
            action_label="Retrieve geospatial data",
            requires_location=True,
        ),
        "requested_concepts": ["earthquakes"],
        "requested_layers": ["usgs_earthquakes"],
        "tools_needed": True,
        "temporal_signal": TemporalSignal(mode="current"),
    }
    payload.update(updates)
    return TurnParseResult.model_validate(payload)


def test_hierarchy_relationship_is_canonical_and_resolved_once() -> None:
    turn = _turn(
        user_text="Show the EUR district in Rome",
        location_signals=[
            LocationSignal(
                signal_type="district",
                raw_value="EUR",
                normalized_value="EUR",
                confidence=0.98,
            ),
            LocationSignal(
                signal_type="city",
                raw_value="Rome",
                normalized_value="Rome",
                confidence=0.97,
            ),
        ],
        geographic_relationships=[
            GeographicRelationship(
                relationship="in",
                target="EUR",
                reference="Rome",
                analysis_scope="administrative_geometry",
            )
        ],
    )
    canonical = RequestInterpreter().compile(
        request_id="request-1",
        turn=turn,
        resolved_location=_location("EUR, Rome, Italy", 41.83, 12.47),
    )

    assert canonical.primary_intent == "geospatial_data_retrieval"
    assert [item.original_text for item in canonical.targets] == ["EUR", "Rome"]
    assert canonical.targets[0].parent_target_ids == [canonical.targets[1].target_id]
    assert canonical.targets[0].resolution_status == "resolved"
    assert canonical.spatial_constraints[0].relationship == "in"
    assert canonical.spatial_constraints[0].analysis_scope == "administrative_geometry"
    assert canonical.map_required is True


def test_peer_targets_keep_distinct_locations_and_scopes() -> None:
    turn = _turn(
        user_text="Compare flooding in Paris and London",
        location_signals=[
            LocationSignal(signal_type="city", raw_value="Paris", normalized_value="Paris"),
            LocationSignal(signal_type="city", raw_value="London", normalized_value="London"),
        ],
        requested_concepts=["flooding"],
        requested_layers=["fema_nfhl_flood_zones"],
        operations=["compare"],
    )
    canonical = RequestInterpreter().compile(
        request_id="request-2",
        turn=turn,
        resolved_locations={
            "paris": _location("Paris, France", 48.8566, 2.3522),
            "london": _location("London, United Kingdom", 51.5074, -0.1278),
        },
    )

    assert [item.peer for item in canonical.targets] == [False, True]
    assert [item.resolved_location.label for item in canonical.targets if item.resolved_location] == [
        "Paris, France",
        "London, United Kingdom",
    ]
    assert {item.target_id for item in canonical.spatial_constraints} == {
        item.target_id for item in canonical.targets
    }
    assert canonical.operations == ["compare", "geospatial_data_retrieval"]


def test_explicit_new_location_is_not_replaced_by_stale_memory() -> None:
    turn = _turn(
        user_text="Actually use Milan",
        location_signals=[
            LocationSignal(signal_type="city", raw_value="Milan", normalized_value="Milan")
        ],
        relationship="correction",
    )
    canonical = RequestInterpreter().compile(
        request_id="request-3",
        turn=turn,
        resolved_location=_location("Milan, Italy", 45.4642, 9.19),
        memory_snapshot={
            "active_location": {
                "label": "Rome, Italy",
                "latitude": 41.9028,
                "longitude": 12.4964,
            }
        },
    )

    assert canonical.primary_target is not None
    assert canonical.primary_target.original_text == "Milan"
    assert canonical.primary_target.resolved_location is not None
    assert canonical.primary_target.resolved_location.label == "Milan, Italy"
    assert "Rome" not in canonical.primary_target.original_text


def test_strongest_is_a_filter_and_does_not_change_domain_or_location() -> None:
    canonical = RequestInterpreter().compile(
        request_id="request-4",
        turn=_turn(user_text="Only the strongest earthquakes in Tokyo"),
        resolved_location=_location("Tokyo, Japan", 35.6762, 139.6503),
    )

    assert canonical.filters["strength_order"] == "descending"
    assert canonical.data_domains == ["earthquakes", "usgs_earthquakes"]
    assert canonical.primary_target is not None
    assert canonical.primary_target.resolved_location is not None
    assert canonical.primary_target.resolved_location.label == "Tokyo, Japan"
    assert "strongest_requires_threshold_or_top_n" in canonical.ambiguities


def test_resolved_location_lookup_uses_geocoder_accent_and_punctuation_folding() -> None:
    turn = _turn(
        user_text="Show earthquakes in São Paulo",
        location_signals=[
            LocationSignal(
                signal_type="city",
                raw_value="São Paulo",
                normalized_value="São Paulo",
            )
        ],
    )
    canonical = RequestInterpreter().compile(
        request_id="request-accent-1",
        turn=turn,
        resolved_locations={
            "sao paulo": _location("São Paulo, Brazil", -23.55, -46.63)
        },
    )

    assert canonical.primary_target is not None
    assert canonical.primary_target.resolution_status == "resolved"
    assert canonical.primary_target.resolved_location is not None
    assert canonical.primary_target.resolved_location.label == "São Paulo, Brazil"


def test_proximity_and_recent_without_defined_defaults_are_ambiguous() -> None:
    canonical = RequestInterpreter().compile(
        request_id="request-ambiguity-1",
        turn=_turn(
            user_text="Show recent earthquakes around Tokyo",
            temporal_signal=TemporalSignal(mode="historical", raw_text="recent"),
            geographic_relationships=[
                GeographicRelationship(
                    relationship="around",
                    target="Tokyo",
                    analysis_scope="radius",
                )
            ],
        ),
        resolved_location=_location("Tokyo, Japan", 35.6762, 139.6503),
    )

    assert "spatial_distance_required" in canonical.ambiguities
    assert "recent_requires_time_window" in canonical.ambiguities


def test_relative_temporal_bounds_resolve_once_in_client_timezone() -> None:
    canonical = RequestInterpreter().compile(
        request_id="request-time-1",
        turn=_turn(
            user_text="Show earthquakes today in Rome",
            temporal_signal=TemporalSignal(mode="historical", raw_text="today"),
        ),
        resolved_location=_location("Rome, Italy", 41.9028, 12.4964),
        request_datetime="2026-09-05T00:30:00Z",
        client_timezone="Europe/Rome",
    )

    temporal = canonical.temporal_constraints
    assert temporal.timezone == "Europe/Rome"
    assert temporal.timezone_source == "client"
    assert temporal.resolved_once is True
    assert temporal.start_time_iso == "2026-09-05T00:00:00+02:00"
    assert temporal.end_time_iso == "2026-09-06T00:00:00+02:00"


def test_invalid_client_timezone_falls_back_to_application_then_utc() -> None:
    application = RequestInterpreter().compile(
        request_id="request-time-2",
        turn=_turn(
            user_text="Show earthquakes yesterday in Rome",
            temporal_signal=TemporalSignal(mode="historical", raw_text="yesterday"),
        ),
        resolved_location=_location("Rome, Italy", 41.9028, 12.4964),
        request_datetime="2026-09-05T12:00:00Z",
        client_timezone="Not/AZone",
        application_timezone="Europe/Rome",
    )
    assert application.temporal_constraints.timezone == "Europe/Rome"
    assert application.temporal_constraints.timezone_source == "application"

    utc = RequestInterpreter().compile(
        request_id="request-time-3",
        turn=_turn(
            user_text="Show earthquakes yesterday in Rome",
            temporal_signal=TemporalSignal(mode="historical", raw_text="yesterday"),
        ),
        resolved_location=_location("Rome, Italy", 41.9028, 12.4964),
        request_datetime="2026-09-05T12:00:00Z",
        client_timezone="Not/AZone",
        application_timezone="Also/NotAZone",
    )
    assert utc.temporal_constraints.timezone == "UTC"
    assert utc.temporal_constraints.timezone_source == "utc"
