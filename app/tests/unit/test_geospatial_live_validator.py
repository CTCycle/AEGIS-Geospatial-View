from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.live_validator import (
    CREDENTIAL_LIVE_CHECKS,
    _run_check,
    validate_live_geospatial_sources,
)
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
        elif provider_id == "overpass":
            payload = {"features": [{"id": "poi-1"}]}
        elif provider_id == "rainviewer":
            payload = {"frameCount": 5, "tileUrl": "https://example.test/{z}/{x}/{y}.png"}
        elif provider_id == "pvgis":
            payload = {"yearlyKwhPerKwpEstimate": 1200.0}
        else:
            payload = {}
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider_id,
            payload=payload,
        )

###############################################################################
def test_live_validator_runs_public_provider_checks_with_injected_registry() -> None:
    report = run_async_in_thread(
        validate_live_geospatial_sources(registry_factory=_LiveValidationRegistry)
    )

    assert report.ok, report.model_dump()
    assert [result.status for result in report.results] == [
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
        "passed",
    ]
    assert {result.provider_id for result in report.results} == {
        "nominatim",
        "usgs",
        "openmeteo",
        "overpass",
        "rainviewer",
        "pvgis",
    }

###############################################################################
def test_live_validator_skips_whitespace_only_credentials(monkeypatch) -> None:
    monkeypatch.setenv("GEOAPIFY_API_KEY", "   ")

    result = run_async_in_thread(_run_check(_LiveValidationRegistry(), CREDENTIAL_LIVE_CHECKS[0]))

    assert result.status == "skipped"
    assert "GEOAPIFY_API_KEY" in (result.message or "")

###############################################################################
def test_live_validator_rejects_error_payloads() -> None:

    ###############################################################################
    class _ErrorRegistry(_LiveValidationRegistry):

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id: str, request: ProviderRequest) -> ProviderResponse:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=provider_id,
                payload={"error": "upstream unavailable"},
            )

    result = run_async_in_thread(
        _run_check(
            _ErrorRegistry(),
            CREDENTIAL_LIVE_CHECKS[0].__class__(
                provider_id="pvgis",
                request=ProviderRequest(capability_id="pvgis_solar_potential"),
            ),
        )
    )

    assert result.status == "failed"
    assert "upstream unavailable" in (result.message or "")
