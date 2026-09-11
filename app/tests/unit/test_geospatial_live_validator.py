from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.live_validator import (
    CREDENTIAL_LIVE_CHECKS,
    PROVIDER_SMOKE_CHECKS,
    _run_check,
    validate_live_geospatial_sources,
)
from server.services.geospatial.provider_registry import PROVIDER_FACTORIES
from server.services.geospatial.providers.base import ProviderRequest, ProviderResponse

###############################################################################
class _LiveValidationRegistry:
    credential_resolver = type(
        "CredentialResolver",
        (),
        {"is_configured": staticmethod(lambda provider_id: False)},
    )()

    # -------------------------------------------------------------------------
    def build_from_manifests(self) -> None:
        return None

    # -------------------------------------------------------------------------
    async def fetch(
        self, provider_id: str, request: ProviderRequest
    ) -> ProviderResponse:
        check = next(
            item for item in PROVIDER_SMOKE_CHECKS if item.provider_id == provider_id
        )
        if check.response_contract == "feature_collection":
            payload = {"features": [{"latitude": 41.9, "longitude": 12.5}]}
        elif check.response_contract == "result_list":
            payload = {"results": [{"latitude": 41.9, "longitude": 12.5}]}
        elif check.response_contract == "raster_metadata":
            payload = {
                "tileUrl": "https://example.test/{z}/{x}/{y}.png",
                "latestTime": "2026-09-08T00:00:00Z",
                "frameCount": 5,
            }
        elif check.response_contract == "dataset":
            payload = {
                "type": "dataset",
                "status": "source-ready",
                "downloadUrl": "https://example.test/data",
                "feeds": [],
                "entities": [],
                "summary": {},
                "catalogRecordCount": 0,
            }
        elif check.response_contract == "metadata":
            payload = {"layer": {}, "render": {}}
        else:
            payload = {"latitude": 41.9, "longitude": 12.5, "current": {}}
            if provider_id == "openmeteo":
                payload["features"] = [
                    {"latitude": 41.9, "longitude": 12.5}
                ]
        for key in check.numeric_payload_keys:
            payload[key] = 1 if key == "frameCount" else 1.0
        for key in check.required_payload_keys:
            if key not in payload:
                payload[key] = (
                    "https://example.test/source"
                    if key.lower().endswith(("url", "path"))
                    else {}
                )
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=provider_id,
            payload=payload,
        )

###############################################################################
def test_live_validator_covers_the_factory_matrix_with_injected_registry() -> None:
    report = run_async_in_thread(
        validate_live_geospatial_sources(registry_factory=_LiveValidationRegistry)
    )

    assert report.ok, report.model_dump()
    assert len(report.results) == len(PROVIDER_SMOKE_CHECKS)
    assert {result.provider_id for result in report.results} == set(PROVIDER_FACTORIES)
    assert all(result.status in {"passed", "skipped"} for result in report.results)

###############################################################################
def test_live_validator_matrix_has_one_case_per_factory_entry() -> None:
    provider_ids = [check.provider_id for check in PROVIDER_SMOKE_CHECKS]

    assert len(provider_ids) == len(set(provider_ids))
    assert set(provider_ids) == set(PROVIDER_FACTORIES)

###############################################################################
def test_live_validator_skips_missing_saved_credentials() -> None:

    result = run_async_in_thread(
        _run_check(_LiveValidationRegistry(), CREDENTIAL_LIVE_CHECKS[0])
    )

    assert result.status == "skipped"
    assert "saved credential" in (result.message or "")

###############################################################################
def test_live_validator_rejects_error_payloads() -> None:

    ###############################################################################
    class _ErrorRegistry(_LiveValidationRegistry):

        # -------------------------------------------------------------------------
        async def fetch(
            self, provider_id: str, request: ProviderRequest
        ) -> ProviderResponse:
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

###############################################################################
def test_live_validator_rejects_malformed_feature_geometry() -> None:

    ###############################################################################
    class _MalformedRegistry(_LiveValidationRegistry):

        # -------------------------------------------------------------------------
        async def fetch(
            self, provider_id: str, request: ProviderRequest
        ) -> ProviderResponse:
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=provider_id,
                payload={"features": [{"id": "missing-geometry"}]},
            )

    result = run_async_in_thread(
        _run_check(
            _MalformedRegistry(),
            PROVIDER_SMOKE_CHECKS[1].__class__(
                provider_id="census",
                request=ProviderRequest(capability_id="census_cartographic_boundaries"),
                response_contract="feature_collection",
                required_payload_keys=("features",),
            ),
        )
    )

    assert result.status == "failed"
    assert "geometry" in (result.message or "")

###############################################################################
def test_live_validator_runs_configured_openchargemap_snapshot(monkeypatch, tmp_path) -> None:
    snapshot = tmp_path / "ocm.json"
    snapshot.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("AEGIS_OCM_SNAPSHOT_PATH", str(snapshot))
    check = next(
        item for item in PROVIDER_SMOKE_CHECKS if item.provider_id == "openchargemap"
    )

    result = run_async_in_thread(_run_check(_LiveValidationRegistry(), check))

    assert result.status == "passed"
