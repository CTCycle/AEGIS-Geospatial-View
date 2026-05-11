from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderAuthError, ProviderRequest
from server.services.geospatial.providers.nrel import NRELProvider
from server.services.geospatial.providers.openchargemap import OpenChargeMapProvider
from server.services.geospatial.providers.opentripmap import OpenTripMapProvider
from server.services.geospatial.providers.ourairports import OurAirportsProvider


def test_opentripmap_requires_key_and_builds_tourism_url() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            OpenTripMapProvider().fetch(
                ProviderRequest(
                    capability_id="opentripmap_tourism_pois",
                    params={"latitude": 41.9, "longitude": 12.5},
                )
            )
        )

    response = asyncio.run(
        OpenTripMapProvider(api_key="tourism-key").fetch(
            ProviderRequest(
                capability_id="opentripmap_tourism_pois",
                params={"latitude": 41.9, "longitude": 12.5, "kinds": "museums"},
            )
        )
    )
    assert response.payload["renderingMode"] == "clustered-points"
    assert "tourism-key" in response.payload["featuresUrl"]
    assert "kinds=museums" in response.payload["featuresUrl"]


def test_openchargemap_supports_optional_key() -> None:
    response = asyncio.run(
        OpenChargeMapProvider().fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    keyed = asyncio.run(
        OpenChargeMapProvider(api_key="charge-key").fetch(
            ProviderRequest(
                capability_id="openchargemap_ev_charging",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    assert "openchargemap" in response.payload["featuresUrl"]
    assert "charge-key" in keyed.payload["featuresUrl"]


def test_nrel_requires_key_for_afdc_descriptor() -> None:
    with pytest.raises(ProviderAuthError):
        asyncio.run(
            NRELProvider().fetch(
                ProviderRequest(
                    capability_id="nrel_afdc_alt_fuel_stations",
                    params={"latitude": 41.9, "longitude": 12.5},
                )
            )
        )

    response = asyncio.run(
        NRELProvider(api_key="nrel-key").fetch(
            ProviderRequest(
                capability_id="nrel_afdc_alt_fuel_stations",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )
    assert "nrel-key" in response.payload["featuresUrl"]
    assert "alt-fuel-stations" in response.payload["featuresUrl"]


def test_ourairports_returns_download_descriptor() -> None:
    response = asyncio.run(
        OurAirportsProvider().fetch(ProviderRequest(capability_id="ourairports_airports"))
    )

    assert response.payload["status"] == "download-required"
    assert response.payload["downloadUrl"].endswith("airports.csv")


def test_provider_registry_binds_phase8_adapters_from_manifests() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    for provider_id in ("opentripmap", "openchargemap", "nrel", "ourairports"):
        assert provider_id in registry.list_provider_ids()
