from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.soilgrids import SoilGridsProvider
from server.services.geospatial.runtime_registry import RuntimeRegistry


###############################################################################
def test_soilgrids_provider_builds_default_wms_and_wcs_descriptors() -> None:
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
    assert "SERVICE=WMS" in response.payload["tileUrl"]
    assert "BBOX={bbox-epsg-3857}" in response.payload["tileUrl"]
    assert "SERVICE=WCS" in response.payload["wcsCapabilitiesUrl"]
    assert "REQUEST=DescribeCoverage" in response.payload["describeCoverageUrl"]
    assert response.payload["spatialResolution"] == "250 m"


###############################################################################
def test_soilgrids_provider_supports_property_depth_and_quantile_selection() -> None:
    response = asyncio.run(
        SoilGridsProvider().fetch(
            ProviderRequest(
                capability_id="soilgrids_soil_properties",
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

    overlay = next(
        item
        for item in loaded["overlays"]
        if item["id"] == "soilgrids_soil_properties"
    )
    profile = next(
        item
        for item in loaded["runtime_profiles"]
        if item["capability_id"] == "soilgrids_soil_properties"
    )

    assert overlay["provider"] == "soilgrids"
    assert overlay["renderingMode"] == "wms"
    assert profile["enabled_by_default"] is True
    assert profile["auth_required"] is False


###############################################################################
def test_soilgrids_is_available_to_runtime_and_provider_registries() -> None:
    runtime_registry = RuntimeRegistry()
    provider_registry = ProviderRegistry()

    assert runtime_registry.is_enabled("soilgrids_soil_properties") is True
    assert runtime_registry.supports_mode("soilgrids_soil_properties", "map") is True
    assert runtime_registry.credentials_present("soilgrids_soil_properties") is True
    assert "soilgrids" in provider_registry.list_provider_ids()
    assert isinstance(provider_registry.get("soilgrids"), SoilGridsProvider)
