from __future__ import annotations

from server.domain.extraction.models import (
    ConversationContextSnapshot,
    LocationSignal,
    NormalizedIntent,
    TurnParseResult,
)
from server.services.agent.manifest_intent_resolver import ManifestIntentResolver
from server.services.agent.manifest_intent_resolver import UserCapabilityAccess
from server.services.agent.manifest_intent_resolver import select_geospatial_capabilities
from server.services.geospatial.capability_registry import CapabilityRegistry


def _turn(text: str, tags: list[str]) -> TurnParseResult:
    return TurnParseResult(
        user_text=text,
        conversation_context=ConversationContextSnapshot(),
        task_class="map_search",
        location_signals=[
            LocationSignal(
                signal_type="coordinates",
                raw_value="41.9,12.5",
                latitude=41.9,
                longitude=12.5,
                confidence=1.0,
            )
        ],
        normalized_intent=NormalizedIntent(
            intent_id="_".join(tags) or "map",
            intent_label=text,
            task_tags=tags,
            intent_tags=tags,
            requested_visualizations=tags,
            requires_location=True,
        ),
        parser_confidence=1.0,
    )


def _resolve(tags: list[str]):
    registry = CapabilityRegistry()
    registry.load_capabilities()
    ids = {
        str(item.get("id"))
        for item in [
            *registry.list_basemaps(),
            *registry.list_overlays(),
            *registry.list_cameras(),
            *registry.list_transit(),
            *registry.list_tools(),
        ]
    }
    return ManifestIntentResolver().resolve(
        turn=_turn(" ".join(tags), tags),
        capability_registry=registry,
        available_ids=ids,
    )


def test_agentic_selection_picks_webcam_capability() -> None:
    resolution = _resolve(["webcams", "near", "mountain", "pass", "road", "condition"])

    assert "windy_webcams" in resolution.overlay_ids


def test_agentic_selection_picks_hospitals_and_shelters_as_poi_capability() -> None:
    resolution = _resolve(["hospitals", "amenities", "shelters"])

    assert set(resolution.overlay_ids).intersection(
        {"overpass_poi_amenities", "geoapify_amenities"}
    )
    assert len(resolution.overlay_ids) <= 4


def test_agentic_selection_restaurants_nearby_stays_poi_only() -> None:
    resolution = _resolve(["restaurants", "nearby", "poi"])

    assert resolution.overlay_ids
    assert set(resolution.overlay_ids).issubset(
        {"overpass_poi_amenities", "geoapify_amenities"}
    )


def test_agentic_selection_general_chat_loads_no_overlays() -> None:
    resolution = _resolve(["joke"])

    assert resolution.overlay_ids == []


def test_agentic_selection_picks_transit_realtime_for_disruptions() -> None:
    resolution = _resolve(["transit", "disruptions", "station"])

    assert "gtfs_realtime" in resolution.overlay_ids


def test_agentic_selection_picks_county_population_layer() -> None:
    resolution = _resolve(["county", "population", "demographics"])

    assert "census_tigerweb_demographics" in resolution.overlay_ids


def test_agentic_selection_picks_hazard_layers_by_need() -> None:
    flood = _resolve(["flood", "shelter", "hazard"])
    fire = _resolve(["fire", "smoke", "route"])

    assert "fema_nfhl_flood_zones" in flood.overlay_ids
    assert "nasa_firms_active_fires" in fire.overlay_ids
    assert set(fire.overlay_ids).intersection(
        {"openmeteo_air_quality_forecast", "openaq_air_quality", "MODIS_Terra_Aerosol"}
    )


def test_agentic_selection_picks_phase8_sources() -> None:
    charging = _resolve(["ev", "charging", "nearby"])
    tourism = _resolve(["tourism", "heritage", "attractions"])
    airport = _resolve(["airport", "aviation", "nearby"])

    assert "openchargemap_ev_charging" in charging.overlay_ids
    assert "opentripmap_tourism_pois" in tourism.overlay_ids
    assert "ourairports_airports" in airport.overlay_ids


def test_select_geospatial_capabilities_gates_missing_location() -> None:
    selected = select_geospatial_capabilities(
        "show flood zones",
        resolved_location=None,
        bbox=None,
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert selected[0].status == "needs-location"


def test_select_geospatial_capabilities_refuses_every_layer() -> None:
    selected = select_geospatial_capabilities(
        "show every possible map layer",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert selected == [
        selected[0].__class__(
            capability_id="category_offer",
            status="refused",
            reason="Indiscriminate layer loading is blocked; offer categories instead.",
        )
    ]


def test_select_geospatial_capabilities_reports_missing_provider_key() -> None:
    selected = select_geospatial_capabilities(
        "show tourism attractions nearby",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert any(
        item.capability_id == "opentripmap_tourism_pois"
        and item.status == "missing-credential"
        for item in selected
    )


def test_select_geospatial_capabilities_prefers_public_alternative_for_restaurants() -> None:
    selected = select_geospatial_capabilities(
        "restaurants nearby",
        resolved_location=object(),
        bbox=(12.0, 41.0, 13.0, 42.0),
        time_context=None,
        user_permissions=UserCapabilityAccess(),
    )

    assert selected
    assert selected[0].capability_id == "overpass_poi_amenities"
    assert selected[0].status == "selected"
