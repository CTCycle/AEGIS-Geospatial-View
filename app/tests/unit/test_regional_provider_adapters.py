from __future__ import annotations

from tests.conftest import run_async_in_thread
import pytest

from server.services.geospatial.cache import GeospatialCache
from server.services.geospatial.providers.base import (
    ProviderRequest,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.eea import EEAProvider
from server.services.geospatial.providers.esa import ESAProvider
from server.services.geospatial.providers.eurostat import EurostatProvider

###############################################################################
def test_eea_provider_returns_wms_descriptor() -> None:
    response = run_async_in_thread(
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
    assert response.result_type == "raster"
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
    first = run_async_in_thread(provider.fetch(request))

    async def failing_fetcher(url: str, headers: dict[str, str] | None = None):
        raise ProviderUnavailableError("timeout")

    clock = 2.0
    provider.fetcher = failing_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert first.payload["liveValidation"]["service"] == "WMS"
    assert stale.stale is True
    assert stale.payload["liveValidation"]["layers"] == ["0"]
    assert stale.warnings

###############################################################################
def test_eea_provider_rejects_malformed_live_validation_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return ["not", "metadata"]

    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            EEAProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eea_noise_2019",
                    params={
                        "live_validate": True,
                        "metadata": {"url": "https://example.test/wms"},
                    },
                )
            )
        )

###############################################################################
def test_esa_provider_returns_wms_descriptor_with_metadata() -> None:
    response = run_async_in_thread(
        ESAProvider().fetch(
            ProviderRequest(
                capability_id="esa_worldcover",
                params={
                    "metadata": {
                        "url": "https://example.test/wms",
                        "layer_id": "esa-worldcover-map-10m-2021-v2_map",
                        "source_protocol": "WMS",
                        "crs": "EPSG:3857",
                        "format": "image/png",
                        "wms_version": "1.3.0",
                        "wms_exceptions": "application/vnd.ogc.se_inimage",
                        "attribution": "ESA",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wms"
    assert response.payload["layerId"] == "esa-worldcover-map-10m-2021-v2_map"
    assert response.payload["layers"] == "esa-worldcover-map-10m-2021-v2_map"
    assert response.payload["serviceUrl"] == "https://example.test/wms"
    assert response.payload["crs"] == "EPSG:3857"
    assert response.payload["format"] == "image/png"
    assert response.payload["version"] == "1.3.0"
    assert response.payload["exceptions"] == "application/vnd.ogc.se_inimage"
    assert response.payload["legend"]["source"] == "ESA WorldCover / Terrascope"
    assert response.payload["freshnessLabel"] == "WorldCover 2021 static source layer"
    assert response.result_type == "raster"
    assert response.attribution == ["ESA"]

###############################################################################
def test_esa_provider_preserves_wmts_descriptor_compatibility() -> None:
    response = run_async_in_thread(
        ESAProvider().fetch(
            ProviderRequest(
                capability_id="esa_worldcover",
                params={
                    "metadata": {
                        "url": "https://example.test/wmts",
                        "source_protocol": "WMTS",
                        "layer_id": "WORLDCOVER_2021_MAP",
                        "tile_matrix_set": "EPSG:3857",
                        "wmts_format": "image/png",
                        "wmts_style": "default",
                    }
                },
            )
        )
    )

    assert response.payload["renderingMode"] == "wmts"
    assert response.payload["serviceUrl"] == "https://example.test/wmts"
    assert response.payload["layerId"] == "WORLDCOVER_2021_MAP"
    assert response.payload["tileMatrixSet"] == "EPSG:3857"
    assert response.payload["format"] == "image/png"
    assert response.payload["style"] == "default"
    assert response.payload["legend"]["source"] == "ESA WorldCover / Terrascope"

###############################################################################
def test_esa_provider_live_validation_handles_timeout_and_stale_cache() -> None:
    clock = 0.0

    def now() -> float:
        return clock

    async def ok_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"service": "WMS", "layers": ["esa-worldcover-map-10m-2021-v2_map"]}

    provider = ESAProvider(
        fetcher=ok_fetcher,
        cache=GeospatialCache(clock=now),
        cache_ttl_seconds=1,
        stale_while_revalidate_seconds=10,
    )
    request = ProviderRequest(
        capability_id="esa_worldcover",
        params={
            "live_validate": True,
            "metadata": {
                "url": "https://example.test/wms",
                "source_protocol": "WMS",
                "layer_id": "esa-worldcover-map-10m-2021-v2_map",
            },
        },
    )
    run_async_in_thread(provider.fetch(request))

    async def timeout_fetcher(url: str, headers: dict[str, str] | None = None):
        raise TimeoutError("timed out")

    clock = 2.0
    provider.fetcher = timeout_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert stale.stale is True
    assert stale.payload["liveValidation"]["service"] == "WMS"

###############################################################################
def test_eurostat_provider_keeps_statistics_metadata_only_until_joined() -> None:
    response = run_async_in_thread(
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
        params={
            "live_validate": True,
            "metadata": {"url": "https://example.test/jsonstat"},
        },
    )
    first = run_async_in_thread(provider.fetch(request))

    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    clock = 2.0
    provider.fetcher = malformed_fetcher
    stale = run_async_in_thread(provider.fetch(request))

    assert first.payload["jsonStatMetadata"]["dimensions"] == ["geo", "time"]
    assert stale.stale is True
    assert stale.payload["jsonStatMetadata"]["label"] == "Population density"

###############################################################################
def test_eurostat_provider_rejects_malformed_jsonstat_without_cache() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None = None):
        return {"value": []}

    with pytest.raises(ProviderUnavailableError):
        run_async_in_thread(
            EurostatProvider(fetcher=malformed_fetcher).fetch(
                ProviderRequest(
                    capability_id="eurostat_regional_demographics",
                    params={
                        "live_validate": True,
                        "metadata": {"url": "https://example.test/jsonstat"},
                    },
                )
            )
        )

###############################################################################
def test_eurostat_provider_builds_fixture_backed_choropleth_payload() -> None:
    response = run_async_in_thread(
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
                                "coordinates": [
                                    [
                                        [12.0, 41.0],
                                        [13.0, 41.0],
                                        [13.0, 42.0],
                                        [12.0, 41.0],
                                    ]
                                ],
                            },
                        },
                        {
                            "type": "Feature",
                            "properties": {"NUTS_ID": "FR", "value": 123.4},
                            "geometry": {
                                "type": "Polygon",
                                "coordinates": [
                                    [[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 48.0]]
                                ],
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
    response = run_async_in_thread(
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
