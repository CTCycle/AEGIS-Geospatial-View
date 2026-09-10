from __future__ import annotations

from server.domain.agent.capability_domains import CapabilityDomain
from server.domain.agent.capability_route import CapabilityRoute
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.capability_registry import CapabilityRegistry


class _RuntimeEligibility:
    def __init__(self, *, disabled: set[str] | None = None) -> None:
        self.disabled = disabled or set()

    def is_enabled(self, capability_id: str) -> bool:
        return capability_id not in self.disabled

    def access_available(self, capability_id: str) -> bool:
        return capability_id not in self.disabled


def _registry() -> CapabilityRegistry:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[
            {
                "id": "traffic",
                "name": "Traffic incidents",
                "provider": "test",
                "capabilityKind": "vector-overlay",
                "description": "Current traffic incidents.",
                "capabilities": ["traffic", "incidents"],
                "agenticUse": {
                    "domains": ["data_retrieval", "map_rendering"],
                    "intentTags": ["traffic"],
                },
            },
            {
                "id": "weather",
                "name": "Weather forecast",
                "provider": "test",
                "capabilityKind": "raster-overlay",
                "description": "Forecast weather tiles.",
                "capabilities": ["weather", "forecast"],
                "agenticUse": {"domains": ["data_retrieval"]},
            },
        ],
        cameras=[],
        transit=[],
        tools=[],
        runtime_profiles=(),
    )
    return CapabilityRegistry.from_catalog_snapshot(snapshot)


def test_shortlist_is_domain_aware_and_bounded() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["weather"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
        limit=25,
    )

    assert [item["id"] for item in candidates] == ["weather", "traffic"]
    assert len(candidates) <= 12
    assert candidates[0]["routing_domains"] == ["data_retrieval"]


def test_explicit_shortlist_ids_are_ranked_and_disabled_ids_are_filtered() -> None:
    candidates = _registry().shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=[],
        explicit_ids=["traffic", "weather"],
        runtime_registry=_RuntimeEligibility(disabled={"traffic"}),
        limit=12,
    )

    assert [item["id"] for item in candidates] == ["weather"]


def test_route_contract_remains_independent_of_provider_arguments() -> None:
    route = CapabilityRoute(
        primary_domain=CapabilityDomain.DATA_RETRIEVAL,
        task_mode="execute",
        presentation="map",
        requires_location=True,
        capability_queries=["traffic"],
    )

    assert "radius_m" not in route.model_dump()


def test_legacy_analysis_tool_is_shortlisted_for_data_retrieval() -> None:
    snapshot = GeospatialManifestSnapshot(
        providers=(),
        basemaps=[],
        overlays=[],
        cameras=[],
        transit=[],
        tools=[
            {
                "id": "weather_direct",
                "name": "Weather Forecast",
                "provider": "openmeteo",
                "capabilityKind": "analysis-tool",
                "description": "Current weather and forecast measurements.",
                "capabilities": ["weather", "forecast"],
            }
        ],
        runtime_profiles=(),
    )
    candidates = CapabilityRegistry.from_catalog_snapshot(snapshot).shortlist(
        domains={CapabilityDomain.DATA_RETRIEVAL},
        queries=["current weather"],
        explicit_ids=[],
        runtime_registry=_RuntimeEligibility(),
    )

    assert [item["id"] for item in candidates] == ["weather_direct"]
