from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider


###############################################################################
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


###############################################################################
def test_eea_provider_live_validation_uses_stale_cache_after_failure() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMS", "layers": ["0"]}

    provider = EEAProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="eea_noise_2019",
        params={"live_validate": True, "metadata": {"url": "https://example.test/wms"}},
    )
    first = asyncio.run(provider.fetch(request))

    async def failing_fetcher(url: str, headers: dict[str, str] | None = None):
        raise ProviderUnavailableError("timeout")

    clock = 2.0
    provider.fetcher = failing_fetcher
    stale = asyncio.run(provider.fetch(request))

    assert first.payload["liveValidation"]["service"] == "WMS"
    assert stale.stale is True
    assert stale.payload["liveValidation"]["layers"] == ["0"]
    assert stale.warnings


###############################################################################
def test_eea_provider_rejects_malformed_live_validation_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return ["not", "metadata"]

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            EEAProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eea_noise_2019",
                    params={"live_validate": True, "metadata": {"url": "https://example.test/wms"}},
                )
            )
        )


###############################################################################
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


###############################################################################
def test_esa_provider_live_validation_handles_timeout_and_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMTS", "tileMatrixSets": ["EPSG3857"]}

    provider = ESAProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="esa_worldcover",
        params={"live_validate": True, "metadata": {"url": "https://example.test/wmts"}},
    )
    asyncio.run(provider.fetch(request))

    async def timeout_fetcher(url: str, headers: dict[str, str] | None = None):
        raise TimeoutError("timed out")

    clock = 2.0
    provider.fetcher = timeout_fetcher
    stale = asyncio.run(provider.fetch(request))

    assert stale.stale is True
    assert stale.payload["liveValidation"]["service"] == "WMTS"


###############################################################################
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


###############################################################################
def test_eurostat_provider_validates_jsonstat_metadata_and_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {
            "label": "Population density",
            "id": ["geo", "time"],
            "size": [1, 1],
            "dimension": {"geo": {}, "time": {}},
            "updated": "2026-01-01",
        }

    provider = EurostatProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="eurostat_regional_demographics",
        params={"live_validate": True, "metadata": {"url": "https://example.test/jsonstat"}},
    )
    first = asyncio.run(provider.fetch(request))

    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    clock = 2.0
    provider.fetcher = malformed_fetcher
    stale = asyncio.run(provider.fetch(request))

    assert first.payload["jsonStatMetadata"]["dimensions"] == ["geo", "time"]
    assert stale.stale is True
    assert stale.payload["jsonStatMetadata"]["label"] == "Population density"


###############################################################################
def test_eurostat_provider_rejects_malformed_jsonstat_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    with pytest.raises(ProviderUnavailableError):
        asyncio.run(
            EurostatProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eurostat_regional_demographics",
                    params={"live_validate": True, "metadata": {"url": "https://example.test/jsonstat"}},
                )
            )
        )


###############################################################################
def test_eurostat_provider_builds_fixture_backed_choropleth_payload() -> None:
    response = asyncio.run(
        EurostatProvider().fetch(
            ProviderRequest(
                capability_id="eurostat_regional_demographics",
                params={
                    "metric": "population_density",
                    "vintage": "2024",
                    "margin_of_error": 1.5,
                    "joined_features": [
                        {
                            "type": "Feature",
                            "properties": {"NUTS_ID": "IT", "value": 201.2},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[12.0, 41.0], [13.0, 41.0], [13.0, 42.0], [12.0, 41.0]]],
                            },
                        },
                        {
                            "type": "Feature",
                            "properties": {"NUTS_ID": "FR", "value": 123.4},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 48.0]]],
                            },
                        },
                    ],
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "choropleth"
    assert response.payload["metric"] == "population_density"
    assert response.payload["vintage"] == "2024"
    assert response.payload["marginOfError"] == 1.5
    assert response.payload["source"] == "Eurostat"
    assert len(response.payload["legendBins"]) == 4
    feature = response.payload["featureCollection"]["features"][0]
    assert feature["properties"]["metric"] == "population_density"
    assert feature["properties"]["marginOfError"] == 1.5


###############################################################################
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


###############################################################################
def test_fred_manifest_remains_metadata_only_without_geographic_join() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    fred = json.loads(
        (repo_root / "resources/catalog/overlays/fred_regional_market_indicators.json").read_text(
            encoding="utf-8"
        )
    )

    assert fred["capabilityKind"] == "metadata-only"
    assert fred["agenticUse"]["manualToggle"] is False


###############################################################################
def test_registry_binds_regional_providers() -> None:
    registry = ProviderRegistry()

    registry.build_from_manifests()

    assert "eea" in registry.list_provider_ids()
    assert "esa" in registry.list_provider_ids()
    assert "eurostat" in registry.list_provider_ids()
