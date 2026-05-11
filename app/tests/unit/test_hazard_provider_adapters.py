from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.fema import FEMAProvider
from server.services.geospatial.providers.nasa_firms import NASAFIRMSProvider
from server.services.geospatial.providers.noaa import NOAAProvider
from server.services.geospatial.providers.usgs import USGSProvider


def test_usgs_provider_builds_earthquake_and_water_urls() -> None:
    earthquake = asyncio.run(
        USGSProvider().fetch(ProviderRequest(capability_id="usgs_earthquakes"))
    )
    water = asyncio.run(
        USGSProvider().fetch(
            ProviderRequest(
                capability_id="usgs_water_gauges",
                bbox=(-78.0, 38.0, -77.0, 39.0),
            )
        )
    )

    assert earthquake.payload["renderingMode"] == "clustered-points"
    assert "earthquake.usgs.gov" in earthquake.payload["featuresUrl"]
    assert "bBox=-78.0%2C38.0%2C-77.0%2C39.0" in water.payload["featuresUrl"]


def test_noaa_provider_builds_alert_radar_and_coops_descriptors() -> None:
    alerts = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_weather_alerts"))
    )
    radar = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_radar"))
    )
    coops = asyncio.run(
        NOAAProvider().fetch(ProviderRequest(capability_id="noaa_coops_water_levels"))
    )

    assert alerts.payload["renderingMode"] == "geojson"
    assert radar.payload["renderingMode"] == "raster-tile"
    assert "tidesandcurrents.noaa.gov" in coops.payload["featuresUrl"]


def test_fema_provider_builds_nfhl_tile_descriptor() -> None:
    response = asyncio.run(
        FEMAProvider().fetch(ProviderRequest(capability_id="fema_nfhl_flood_zones"))
    )

    assert response.payload["renderingMode"] == "wms"
    assert "hazards.fema.gov" in response.payload["tileUrl"]


def test_nasa_firms_requires_key_before_descriptor() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            NASAFIRMSProvider().fetch(
                ProviderRequest(
                    capability_id="nasa_firms_active_fires",
                    bbox=(-123.0, 38.0, -121.0, 40.0),
                )
            )
        )

    response = asyncio.run(
        NASAFIRMSProvider(api_key="test-key").fetch(
            ProviderRequest(
                capability_id="nasa_firms_active_fires",
                bbox=(-123.0, 38.0, -121.0, 40.0),
            )
        )
    )
    assert "test-key" in response.payload["featuresUrl"]


def test_provider_registry_binds_hazard_adapters_from_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    for provider_id in ("usgs", "noaa", "fema", "nasa_firms"):
        assert provider_id in registry.list_provider_ids()
