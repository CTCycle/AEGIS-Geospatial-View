from __future__ import annotations

import asyncio

from server.services.geospatial.live_validator import validate_live_geospatial_sources
from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse


###############################################################################
class _LiveValidationRegistry:

    # -------------------------------------------------------------------------
    def build_from_manifests(self) -> None:
        return None

    # -------------------------------------------------------------------------
    async def fetch(self, provider_id: str, request: ProviderRequest) -> ProviderResponse:
        if provider_id == "nominatim":
            payload = {"results": [{"latitude": 41.9, "longitude": 12.5}]}
        elif provider_id == "usgs":
            payload = {"features": [{"id": "quake-1"}]}
        elif provider_id == "openmeteo":
            payload = {"current": {"temperature": 20}, "features": []}
        else:
            payload = {}
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider_id,
            payload=payload,
        )


###############################################################################
def test_live_validator_runs_public_provider_checks_with_injected_registry() -> None:
    report = asyncio.run(
        validate_live_geospatial_sources(registry_factory=_LiveValidationRegistry)
    )

    assert report.ok, report.model_dump()
    assert [result.status for result in report.results] == ["passed", "passed", "passed"]
    assert {result.provider_id for result in report.results} == {
        "nominatim",
        "usgs",
        "openmeteo",
    }
