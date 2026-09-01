from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.soilgrids import SoilGridsProvider
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def test_soilgrids_provider_builds_default_wcs_descriptors() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(capability_id="soilgrids_soil_properties")
        )
    )

    assert response.provider_id == "soilgrids"
    assert response.payload["property"] == "phh2o"
    assert response.payload["depth"] == "0-5cm"
    assert response.payload["quantile"] == "mean"
    assert response.payload["coverageId"] == "phh2o_0-5cm_mean"
    assert response.payload["renderingMode"] == "metadata-only"
    assert "SERVICE=WCS" in response.payload["wcsCapabilitiesUrl"]
    assert "REQUEST=DescribeCoverage" in response.payload["describeCoverageUrl"]
    assert response.payload["coverageDownloadUrl"] is None
    assert response.payload["spatialResolution"] == "250 m"


###############################################################################
def test_soilgrids_provider_builds_bounded_geotiff_coverage_url() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(
                capability_id="soilgrids_soil_properties",
                bbox=(8.50, 47.35, 8.60, 47.45),
                params={
                    "property": "clay",
                    "depth": "30-60cm",
                    "quantile": "Q0.95",
                },
            )
        )
    )

    assert response.payload["coverageId"] == "clay_30-60cm_Q0.95"
    assert response.payload["propertyLabel"] == "Clay"
    assert response.payload["mappedUnit"] == "g/kg"
    assert response.payload["conversionFactor"] == 10
    coverage_url = response.payload["coverageDownloadUrl"]
    assert coverage_url is not None
    assert "REQUEST=GetCoverage" in coverage_url
    assert "COVERAGEID=clay_30-60cm_Q0.95" in coverage_url
    assert "FORMAT=GEOTIFF_INT16" in coverage_url
    assert "SUBSETTINGCRS=" in coverage_url
    assert coverage_url.count("SUBSET=") == 2


###############################################################################
def test_soilgrids_provider_handles_organic_carbon_stock_depth_constraints() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(
                capability_id="soilgrids_soil_properties",
                params={"property": "ocs", "depth": "0-30cm", "quantile": "mean"},
            )
        )
    )

    assert response.payload["coverageId"] == "ocs_0-30cm_mean"
    assert response.payload["availableDepths"] == ["0-30cm"]
    assert response.payload["availableQuantiles"] == ["mean"]


###############################################################################
def test_soilgrids_provider_rejects_unknown_property() -> None:
    with pytest.raises(ProviderUnavailableError, match="Unsupported SoilGrids property"):
        asyncio.run(
            SoilGridsProvider().fetch(
                ProviderRequest(
                    capability_id="soilgrids_soil_properties",
                    params={"property": "not-a-soil-property"},
                )
            )
        )


###############################################################################
def test_soilgrids_manifest_and_runtime_profile_are_loaded() -> None:
    loaded = GeospatialManifestLoader().load_all()

    capability = next(
        item
        for item in loaded["overlays"]
        if item["id"] == "soilgrids_soil_properties"
    )
    profile = next(
        item
        for item in loaded["runtime_profiles"]
        if item["capability_id"] == "soilgrids_soil_properties"
    )

    assert capability["provider"] == "soilgrids"
    assert capability["capabilityKind"] == "analysis-tool"
    assert capability["renderingMode"] == "metadata-only"
    assert profile["enabled_by_default"] is True
    assert profile["supports_map"] is False
    assert profile["supports_direct_text"] is True
    assert profile["auth_required"] is False


###############################################################################
def test_soilgrids_is_available_to_runtime_and_provider_registries() -> None:
    runtime_registry = RuntimeRegistry()
    provider_registry = ProviderRegistry()

    assert runtime_registry.is_enabled("soilgrids_soil_properties") is True
    assert runtime_registry.supports_mode("soilgrids_soil_properties", "map") is False
    assert runtime_registry.supports_mode("soilgrids_soil_properties", "text") is True
    assert runtime_registry.credentials_present("soilgrids_soil_properties") is True
    assert "soilgrids" in provider_registry.list_provider_ids()
    assert isinstance(provider_registry.get("soilgrids"), SoilGridsProvider)
