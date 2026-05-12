from __future__ import annotations

import asyncio

from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider


def test_eea_provider_returns_wms_descriptor() -> None:
    response = asyncio.run(
        EEAProvider().fetch(
            ProviderRequest(
                capability_id="eea_noise_2019",
                params={
                    "metadata": {
                        "url": "https://example.test/wms",
                        "layers": "0",
                        "attribution": "EEA",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wms"
    assert response.payload["serviceUrl"] == "https://example.test/wms"
    assert response.payload["layers"] == ["0"]
    assert response.attribution == ["EEA"]


def test_esa_provider_returns_wmts_descriptor() -> None:
    response = asyncio.run(
        ESAProvider().fetch(
            ProviderRequest(
                capability_id="esa_worldcover",
                params={
                    "metadata": {
                        "url": "https://example.test/wmts",
                        "layer_id": "WORLDCOVER_2021_MAP",
                        "attribution": "ESA",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wmts"
    assert response.payload["layerId"] == "WORLDCOVER_2021_MAP"
    assert response.payload["serviceUrl"] == "https://example.test/wmts"
    assert response.attribution == ["ESA"]


def test_eurostat_provider_keeps_statistics_metadata_only_until_joined() -> None:
    response = asyncio.run(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_regional_demographics",
                params={"metadata": {"url": "https://example.test/jsonstat"}},
            )
        )
    )

    assert response.payload["renderingMode"] == "metadata-only"
    assert response.payload["joinRequired"] is True
    assert response.payload["joinKey"] == "NUTS_ID"


def test_eurostat_provider_describes_nuts_ingestion_payload() -> None:
    response = asyncio.run(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_nuts_regions",
                params={"source_url": "https://example.test/nuts.geojson"},
            )
        )
    )

    assert response.payload["renderingMode"] == "vector-tile"
    assert response.payload["status"] == "dataset-ingestion"
    assert response.payload["joinKey"] == "NUTS_ID"


def test_registry_binds_regional_providers() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "eea" in registry.list_provider_ids()
    assert "esa" in registry.list_provider_ids()
    assert "eurostat" in registry.list_provider_ids()
