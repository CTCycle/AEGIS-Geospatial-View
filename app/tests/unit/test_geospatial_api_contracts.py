from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server.api import geospatial
from server.api.geospatial import raise_service_http_error
from server.app import create_app
from server.contracts.geospatial import (
    GeospatialLayerRenderDescriptor,
    GeospatialProviderLayerDescriptor,
)
from server.domain.geospatial.providers import ProviderResponse
from server.domain.geospatial.registry import GeospatialManifestSnapshot
from server.services.geospatial.api_service import (
    GeospatialApiService,
    GeospatialApiServiceError,
    GeospatialCapabilityNotFoundError,
    GeospatialInvalidRequestError,
    GeospatialTileCredentialError,
    GeospatialTileRequestError,
    GeospatialUnsupportedTileError,
)
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.catalog import GeospatialCatalogService
from server.services.geospatial.manifest_loader import GeospatialManifestLoader
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.rainviewer import RainViewerService
from server.services.geospatial.runtime_registry import RuntimeRegistry
from server.services.geospatial.providers.base import (
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from server.services.geospatial.providers.http import (
    RasterHttpDiagnostic,
    RasterHttpError,
)
from server.services.geospatial.raster_tiles import web_mercator_tile_bbox

###############################################################################
def create_started_client() -> TestClient:
    client = TestClient(create_app())
    client.__enter__()
    return client

###############################################################################
class _NoCredentials:

    # -------------------------------------------------------------------------
    def get_active(self, *, provider: str, label: str):  # noqa: ANN201
        return None

###############################################################################
def _build_api_service(
    provider_registry, *, rainviewer_service: RainViewerService | None = None
) -> GeospatialApiService:  # noqa: ANN001
    manifest_loader = GeospatialManifestLoader()
    runtime_registry = RuntimeRegistry(
        manifest_loader=manifest_loader,
        credentials_repo=_NoCredentials(),  # type: ignore[arg-type]
    )
    return GeospatialApiService(
        catalog_service=GeospatialCatalogService(
            capability_registry=CapabilityRegistry(manifest_loader=manifest_loader),
            runtime_registry=runtime_registry,
        ),
        manifest_loader=manifest_loader,
        runtime_registry=runtime_registry,
        provider_registry=provider_registry,
        rainviewer_service=rainviewer_service,
    )

###############################################################################
def test_geospatial_transit_features_return_metadata_until_feed_configured() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/layers/gtfs_realtime/features")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["payload"]["renderingMode"] == "metadata-only"

###############################################################################
def test_geospatial_features_reports_missing_credentials_without_500() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/layers/tomtom_traffic_flow/features")

    assert response.status_code == 200
    assert response.json()["status"] in {"missing-credential", "ok"}

###############################################################################
def test_geospatial_features_render_contract_still_uses_provider_envelope() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/layers/usgs_earthquakes/features?live=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "unavailable"}
    assert "payload" in payload

###############################################################################
def test_geospatial_geojson_render_endpoint_returns_raw_feature_collection() -> None:

    ###############################################################################
    class GeoJsonRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            return type(
                "Response",
                (),
                {
                    "payload": {
                        "type": "FeatureCollection",
                        "features": [
                            {
                                "type": "Feature",
                                "id": "quake-1",
                                "properties": {"mag": 2.4},
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [12.5, 41.9],
                                },
                            }
                        ],
                    },
                    "attribution": ["USGS"],
                    "warnings": [],
                    "stale": False,
                },
            )()

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(GeoJsonRegistry())
    )

    response = client.get("/api/geospatial/layers/usgs_earthquakes/geojson?live=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["id"] == "quake-1"

###############################################################################
def test_geospatial_geojson_render_endpoint_wraps_single_feature() -> None:

    ###############################################################################
    class SingleFeatureRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            return type(
                "Response",
                (),
                {
                    "payload": {
                        "type": "Feature",
                        "id": "quake-1",
                        "properties": {"mag": 2.4},
                        "geometry": {
                            "type": "Point",
                            "coordinates": [12.5, 41.9],
                        },
                    },
                    "attribution": ["USGS"],
                    "warnings": [],
                    "stale": False,
                },
            )()

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(SingleFeatureRegistry())
    )

    response = client.get("/api/geospatial/layers/usgs_earthquakes/geojson?live=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    assert payload["features"][0]["id"] == "quake-1"

###############################################################################
def test_geospatial_geojson_render_endpoint_converts_normalized_point_records() -> None:

    ###############################################################################
    class NormalizedPointRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            return type(
                "Response",
                (),
                {
                    "payload": {
                        "renderingMode": "clustered-points",
                        "features": [
                            {
                                "id": "gauge-1",
                                "name": "Gauge 1",
                                "latitude": 41.9,
                                "longitude": 12.5,
                                "value": 1.25,
                            }
                        ],
                    },
                    "attribution": ["USGS"],
                    "warnings": [],
                    "stale": False,
                },
            )()

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(NormalizedPointRegistry())
    )

    response = client.get("/api/geospatial/layers/usgs_water_gauges/geojson?live=true")

    assert response.status_code == 200
    feature = response.json()["features"][0]
    assert feature["geometry"] == {"type": "Point", "coordinates": [12.5, 41.9]}
    assert feature["properties"] == {"name": "Gauge 1", "value": 1.25}

###############################################################################
def test_geospatial_cameras_geojson_render_endpoint_returns_raw_feature_collection() -> (
    None
):

    ###############################################################################
    class CameraRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            return type(
                "Response",
                (),
                {
                    "payload": {
                        "renderingMode": "camera-points",
                        "features": [
                            {
                                "type": "Feature",
                                "id": "cam-1",
                                "properties": {"name": "Camera 1"},
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [12.5, 41.9],
                                },
                            }
                        ],
                    },
                    "attribution": ["Windy Webcams"],
                    "warnings": [],
                    "stale": False,
                },
            )()

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(CameraRegistry())
    )

    response = client.get("/api/geospatial/cameras.geojson?bbox=12,41,13,42")

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "FeatureCollection"
    assert payload["features"][0]["id"] == "cam-1"

###############################################################################
def test_geospatial_geojson_render_endpoint_rejects_malformed_payload() -> None:

    ###############################################################################
    class MalformedRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            return type(
                "Response",
                (),
                {
                    "payload": {"status": "not-geojson", "items": [1, 2, 3]},
                    "attribution": ["USGS"],
                    "warnings": ["malformed upstream payload"],
                    "stale": False,
                },
            )()

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(MalformedRegistry())
    )

    response = client.get("/api/geospatial/layers/usgs_earthquakes/geojson?live=true")

    assert response.status_code == 502
    assert response.json()["detail"]["error_code"] == "malformed_response"

###############################################################################
def test_geospatial_tile_proxy_rejects_missing_credentials_without_leaking_secret(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    client = create_started_client()

    response = client.get("/api/geospatial/tiles/tomtom_traffic_flow/1/0/0.png")

    assert response.status_code == 401
    assert "TOMTOM_API_KEY" not in response.text

###############################################################################
def test_geospatial_tile_proxy_ignores_environment_credentials(
    monkeypatch,
) -> None:
    captured: dict[str, str] = {}

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured["url"] = url
        return b"tile-binary"

    monkeypatch.setenv("TOMTOM_API_KEY", "tomtom-secret-forbidden")
    service = _build_api_service(
        ProviderRegistry(manifest_loader=GeospatialManifestLoader())
    )
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/tomtom_traffic_flow/4/5/6.png")

    assert response.status_code == 401
    assert captured == {}
    assert "tomtom-secret-forbidden" not in response.text

###############################################################################
def test_raster_tile_utility_returns_exact_web_mercator_bbox() -> None:
    assert web_mercator_tile_bbox(1, 1, 1) == (
        0.0,
        -20037508.342789244,
        20037508.342789244,
        0.0,
    )

###############################################################################
def test_geospatial_fema_tile_proxy_materializes_bounded_export_request() -> None:
    captured: dict[str, str] = {}

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured["url"] = url
        captured["headers"] = headers or {}
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/fema_nfhl_flood_zones/1/1/1.png")

    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    parsed = urlsplit(captured["url"])
    query = parse_qs(parsed.query)
    assert parsed.netloc == "hazards-fema.maps.arcgis.com"
    assert parsed.path == "/sharing/proxy"
    assert query["bboxSR"] == ["3857"]
    assert query["imageSR"] == ["3857"]
    assert query["size"] == ["256,256"]
    assert query["format"] == ["png32"]
    assert query["transparent"] == ["true"]
    assert query["f"] == ["image"]
    inner_url = next(
        key
        for key in query
        if key.startswith(
            "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export"
        )
    )
    assert inner_url == (
        "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/export?bbox"
    )
    assert query[inner_url] == [
        ",".join(str(value) for value in web_mercator_tile_bbox(1, 1, 1))
    ]
    headers = captured["headers"]
    assert headers["Origin"] == "https://hazards-fema.maps.arcgis.com"
    assert "webappviewer" in headers["Referer"]

###############################################################################
def test_relay_config_validates_manifest_relay_transport() -> None:
    service = _build_api_service(ProviderRegistry())

    valid = service._relay_config(
        {
            "relay": {
                "base_url": "https://hazards-fema.maps.arcgis.com/sharing/proxy",
                "required_headers": {
                    "Origin": "https://hazards-fema.maps.arcgis.com",
                    "Referer": "https://hazards-fema.maps.arcgis.com/apps/viewer/index.html",
                },
            }
        }
    )
    assert valid is not None
    assert valid["base_url"] == "https://hazards-fema.maps.arcgis.com/sharing/proxy"
    assert valid["required_headers"]["Origin"].startswith("https://")

    assert (
        service._relay_config(
            {
                "relay": {
                    "base_url": "http://hazards-fema.maps.arcgis.com/sharing/proxy",
                    "required_headers": {"Origin": "https://example.com"},
                }
            }
        )
        is None
    )
    assert (
        service._relay_config(
            {
                "relay": {
                    "base_url": "https://untrusted.example/sharing/proxy",
                    "required_headers": {"Origin": "https://example.com"},
                }
            }
        )
        is None
    )
    assert (
        service._relay_config(
            {"relay": {"base_url": "https://hazards-fema.maps.arcgis.com/sharing/proxy"}}
        )
        is None
    )
    assert service._relay_config({"relay": None}) is None
    assert service._relay_config({"relay": {"base_url": "not-a-url"}}) is None
    assert service._relay_config({}) is None

###############################################################################
def test_geospatial_esa_tile_proxy_materializes_bounded_wms_get_map_request() -> None:
    captured: dict[str, str] = {}

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured["url"] = url
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/esa_worldcover/4/5/6.png")

    assert response.status_code == 200
    parsed = urlsplit(captured["url"])
    query = parse_qs(parsed.query)
    assert parsed.netloc == "mapproxy.terrascope.be"
    assert parsed.path == "/mapproxy/service"
    assert query["service"] == ["WMS"]
    assert query["request"] == ["GetMap"]
    assert query["layers"] == ["esa-worldcover-map-10m-2021-v2_map"]
    assert query["crs"] == ["EPSG:3857"]
    assert query["version"] == ["1.3.0"]
    assert query["format"] == ["image/png"]
    assert query["transparent"] == ["true"]
    assert query["width"] == ["256"]
    assert query["height"] == ["256"]
    assert "time" not in query
    assert query["bbox"] == [
        ",".join(str(value) for value in web_mercator_tile_bbox(4, 5, 6))
    ]
    assert query["exceptions"] == ["application/vnd.ogc.se_inimage"]
    assert "tilematrix" not in query

###############################################################################
def test_geospatial_gibs_tile_proxy_uses_provider_descriptor_and_requested_time() -> None:
    captured: dict[str, str] = {}

    class GibsRegistry:

        async def describe_layer(self, provider_id: str, layer_id: str):
            assert provider_id == "gibs"
            assert layer_id == "MODIS_Terra_NDVI_8Day"
            return GeospatialProviderLayerDescriptor(
                provider="gibs",
                layer_id=layer_id,
                title="MODIS Terra NDVI 8-Day",
                rendering_mode="wmts",
                source_protocol="wmts",
                data_format="image/png",
                geometry_type="raster-grid",
                default_time="2026-06-18",
                tile_matrix_sets=["GoogleMapsCompatible_Level9"],
                render=GeospatialLayerRenderDescriptor(
                    provider="gibs",
                    layer_id=layer_id,
                    rendering_mode="wmts",
                    source_protocol="wmts",
                    url="https://gibs.earthdata.nasa.gov/wmts/epsg3857/best",
                    tile_url_template=(
                        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                        "MODIS_Terra_NDVI_8Day/default/{time}/"
                        "GoogleMapsCompatible_Level9/{z}/{y}/{x}.png"
                    ),
                    tile_matrix_set="GoogleMapsCompatible_Level9",
                    format="image/png",
                    default_time="2026-06-18",
                ),
            )

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured["url"] = url
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(GibsRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get(
        "/api/geospatial/tiles/gibs:MODIS_Terra_NDVI_8Day/2/1/3.png"
        "?time=2026-06-20"
    )

    assert response.status_code == 200
    assert captured["url"] == (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        "MODIS_Terra_NDVI_8Day/default/2026-06-20/"
        "GoogleMapsCompatible_Level9/2/3/1.png"
    )

###############################################################################
def test_geospatial_gibs_stable_capability_maps_to_provider_layer_and_time() -> None:
    captured: dict[str, str] = {}

    class GibsRegistry:

        async def describe_layer(self, provider_id: str, layer_id: str):
            assert provider_id == "gibs"
            assert layer_id == "MODIS_Combined_Thermal_Anomalies_All"
            captured["provider_id"] = provider_id
            captured["layer_id"] = layer_id
            return GeospatialProviderLayerDescriptor(
                provider="gibs",
                layer_id=layer_id,
                title="MODIS Combined Thermal Anomalies",
                rendering_mode="wms",
                source_protocol="wms",
                data_format="image/png",
                geometry_type="raster-grid",
                default_time="2026-09-27",
                render=GeospatialLayerRenderDescriptor(
                    provider="gibs",
                    layer_id=layer_id,
                    rendering_mode="wms",
                    source_protocol="wms",
                    url="https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
                    crs="EPSG:3857",
                    format="image/png",
                    default_time="2026-09-27",
                    attribution=["© NASA GIBS"],
                ),
                attribution=["© NASA GIBS"],
            )

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured["url"] = url
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(GibsRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get(
        "/api/geospatial/tiles/MODIS_Combined_Thermal_Anomalies_Fire/2/1/3.png"
        "?time=2026-09-28"
    )

    assert response.status_code == 200
    parsed = urlsplit(captured["url"])
    query = parse_qs(parsed.query)
    assert parsed.netloc == "gibs.earthdata.nasa.gov"
    assert query["service"] == ["WMS"]
    assert query["request"] == ["GetMap"]
    assert query["layers"] == ["MODIS_Combined_Thermal_Anomalies_All"]
    assert query["crs"] == ["EPSG:3857"]
    assert query["version"] == ["1.3.0"]
    assert query["format"] == ["image/png"]
    assert query["transparent"] == ["true"]
    assert query["width"] == ["256"]
    assert query["height"] == ["256"]
    assert query["time"] == ["2026-09-28"]
    assert query["bbox"] == [
        ",".join(str(value) for value in web_mercator_tile_bbox(2, 1, 3))
    ]

###############################################################################
def test_geospatial_tile_proxy_rejects_malformed_coordinates_before_network() -> None:
    captured: list[str] = []

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured.append(url)
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/esa_worldcover/2/4/0.png")

    assert response.status_code == 400
    assert captured == []

###############################################################################
def test_geospatial_tile_proxy_rejects_unresolved_template_before_network() -> None:
    captured: list[str] = []

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured.append(url)
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(ProviderRegistry())
    service.catalog_snapshot = GeospatialManifestSnapshot.from_payload(
        {
            "overlays": [
                {
                    "id": "fixture_raster",
                    "provider": "fixture",
                    "type": "raster-overlay",
                    "renderingMode": "raster-tile",
                    "metadata": {
                        "url_template": "https://known.example/{z}/{unknown}/{y}.png"
                    },
                }
            ]
        }
    )
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/fixture_raster/2/1/1.png")

    assert response.status_code == 404
    assert captured == []

###############################################################################
def test_geospatial_tile_proxy_rejects_unknown_capability_without_network() -> None:
    captured: list[str] = []

    async def fake_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        captured.append(url)
        return b"\x89PNG\r\n\x1a\npng-tile"

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = fake_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/not-a-capability/1/0/0.png")

    assert response.status_code == 404
    assert captured == []
    assert "evil.example" not in response.text

###############################################################################
@pytest.mark.parametrize(
    "provider_error",
    [
        ProviderTimeoutError("sensitive-timeout-token"),
        ProviderUnavailableError("sensitive-upstream-detail"),
    ],
)
def test_geospatial_tile_proxy_normalizes_upstream_failures_without_details(
    provider_error: Exception,
) -> None:
    async def failing_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        del url
        raise provider_error

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = failing_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get("/api/geospatial/tiles/esa_worldcover/4/5/6.png")

    assert response.status_code == 502
    assert "sensitive" not in response.text

###############################################################################
def test_geospatial_tile_proxy_rejects_non_image_http_200_body(monkeypatch) -> None:
    async def fake_fetch_raster_image_url(url: str, headers: dict[str, str]) -> bytes:
        del url, headers
        return b"<html>provider error</html>"

    monkeypatch.setattr(
        "server.services.geospatial.api_service.fetch_raster_image_url",
        fake_fetch_raster_image_url,
    )
    client = create_started_client()

    response = client.get("/api/geospatial/tiles/esa_worldcover/4/5/6.png")

    assert response.status_code == 502
    assert "provider error" not in response.text


def test_geospatial_tile_proxy_logs_safe_raster_diagnostic_and_normalizes_response(
    caplog: pytest.LogCaptureFixture,
) -> None:
    diagnostic = RasterHttpDiagnostic(
        category="upstream_http_5xx",
        failure_phase="response_headers",
        upstream="https://fema.example/arcgis/tile",
        status_code=503,
        content_type="text/html",
        content_length=42,
        provider_id="fema",
        capability_id="fema_nfhl_flood_zones",
    )

    async def failing_fetch_binary_url(
        url: str, headers: dict[str, str] | None = None
    ) -> bytes:
        del url
        raise RasterHttpError("secret provider response", diagnostic)

    service = _build_api_service(ProviderRegistry())
    service._fetch_binary_url = failing_fetch_binary_url  # type: ignore[method-assign]
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    with caplog.at_level(logging.WARNING, logger="server.services.geospatial.api_service"):
        response = client.get(
            "/api/geospatial/tiles/fema_nfhl_flood_zones/4/5/6.png"
            "?api_key=secret-token"
        )

    assert response.status_code == 502
    assert "secret" not in response.text.lower()
    assert "secret" not in caplog.text.lower()
    assert "category=upstream_http_5xx" in caplog.text
    assert "provider=fema" in caplog.text
    assert "capability=fema_nfhl_flood_zones" in caplog.text
    assert "status=503" in caplog.text
    assert "content_type=text/html" in caplog.text
    assert "content_length=42" in caplog.text
    assert "upstream=https://fema.example/arcgis/tile" in caplog.text

###############################################################################
def test_geospatial_tile_proxy_sanitizes_sensitive_query_values_in_logs() -> None:
    sanitized = GeospatialApiService._sanitize_tile_url(
        "https://known.example/tile.png?api_key=secret-value&format=image/png"
    )

    assert "secret-value" not in sanitized
    assert "api_key=%5BREDACTED%5D" in sanitized
    assert "format=image%2Fpng" in sanitized

###############################################################################
def test_rainviewer_tile_proxy_uses_cached_latest_metadata_and_same_origin_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata_calls: list[str] = []
    tile_calls: list[str] = []

    async def metadata_fetcher(
        url: str, headers: dict[str, str] | None = None
    ) -> dict[str, object]:
        metadata_calls.append(url)
        _ = headers
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {"past": [{"time": 200, "path": "/v2/radar/200"}]},
        }

    async def tile_fetcher(url: str, headers: dict[str, str]) -> bytes:
        tile_calls.append(url)
        _ = headers
        return b"\x89PNG\r\n\x1a\npng"

    monkeypatch.setattr(
        "server.services.geospatial.api_service.fetch_raster_image_url",
        tile_fetcher,
    )
    service = _build_api_service(
        ProviderRegistry(),
        rainviewer_service=RainViewerService(fetcher=metadata_fetcher),
    )
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    first = client.get(
        "/api/geospatial/tiles/rainviewer_precipitation_radar/7/64/48.png"
    )
    second = client.get(
        "/api/geospatial/tiles/rainviewer_precipitation_radar/7/65/48.png"
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.headers["content-type"].startswith("image/png")
    assert metadata_calls == ["https://api.rainviewer.com/public/weather-maps.json"]
    assert tile_calls == [
        "https://tilecache.rainviewer.com/v2/radar/200/256/7/64/48/2/1_1.png",
        "https://tilecache.rainviewer.com/v2/radar/200/256/7/65/48/2/1_1.png",
    ]


@pytest.mark.parametrize(
    "suffix",
    ["/8/128/128.png", "/7/64/48.png?time=2026-09-30T12:00:00Z"],
)
def test_rainviewer_tile_proxy_rejects_unsupported_zoom_and_forecast_time(
    suffix: str,
) -> None:
    service = _build_api_service(ProviderRegistry())
    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        service
    )

    response = client.get(
        f"/api/geospatial/tiles/rainviewer_precipitation_radar{suffix}"
    )

    assert response.status_code == 404

###############################################################################
def test_geospatial_features_accepts_live_provider_flags_without_500() -> None:
    client = create_started_client()

    response = client.get(
        "/api/geospatial/layers/tomtom_traffic_flow/features"
        "?bbox=12,41,13,42&live=true&incidents=true"
    )

    assert response.status_code == 200
    assert response.json()["status"] in {"missing-credential", "ok", "unavailable"}

###############################################################################
def test_geospatial_raster_features_forward_manifest_metadata_to_provider() -> None:
    captured: dict[str, object] = {}

    class MetadataRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            captured["provider_id"] = provider_id
            captured["request"] = request
            return ProviderResponse(
                capability_id=request.capability_id,
                provider_id=provider_id,
                payload={
                    "renderingMode": "wms",
                    "serviceUrl": request.params["metadata"]["url"],
                    "layerId": request.params["metadata"]["layer_id"],
                },
                result_type="raster",
            )

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(MetadataRegistry())
    )

    response = client.get("/api/geospatial/layers/esa_worldcover/features")

    assert response.status_code == 200
    assert response.json()["payload"]["serviceUrl"] == (
        "https://mapproxy.terrascope.be/mapproxy/service"
    )
    assert response.json()["payload"]["layerId"] == (
        "esa-worldcover-map-10m-2021-v2_map"
    )
    request = captured["request"]
    assert request.params["metadata"]["url"] == (  # type: ignore[attr-defined]
        "https://mapproxy.terrascope.be/mapproxy/service"
    )
    assert request.params["metadata"]["layer_id"] == (  # type: ignore[attr-defined]
        "esa-worldcover-map-10m-2021-v2_map"
    )

###############################################################################
@pytest.mark.parametrize(
    ("provider_error", "expected_status"),
    [
        (ProviderRateLimitError("provider quota exceeded"), "rate-limited"),
        (ProviderTimeoutError("provider request timed out"), "unavailable"),
    ],
)
def test_geospatial_features_map_provider_failures_without_500(
    monkeypatch, provider_error: Exception, expected_status: str
) -> None:

    ###############################################################################
    class FailingRegistry:

        # -------------------------------------------------------------------------
        def build_from_manifests(self) -> None:
            return None

        # -------------------------------------------------------------------------
        async def fetch(self, provider_id, request):
            del provider_id, request
            raise provider_error

    client = create_started_client()
    client.app.dependency_overrides[geospatial.get_geospatial_api_service] = lambda: (
        _build_api_service(FailingRegistry())
    )

    response = client.get("/api/geospatial/layers/usgs_earthquakes/features?live=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected_status
    assert payload["provider"] == "usgs"

###############################################################################
def test_geospatial_cameras_report_missing_windy_key_without_500(monkeypatch) -> None:
    monkeypatch.delenv("WINDY_WEBCAMS_API_KEY", raising=False)
    client = create_started_client()

    response = client.get("/api/geospatial/cameras?bbox=12,41,13,42")

    assert response.status_code == 200
    assert response.json()["status"] == "missing-credential"

###############################################################################
def test_geospatial_camera_detail_returns_provider_payload_shape() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/cameras/windy_webcams%2Fcamera-1")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "windy_webcams/camera-1"
    assert payload["status"] in {"missing-credential", "metadata-unavailable", "ok"}
    assert payload["provider"] == "windy_webcams"

###############################################################################
def test_geospatial_credential_status_ignores_environment_variables(
    monkeypatch,
) -> None:
    monkeypatch.setenv("WINDY_WEBCAMS_API_KEY", "test-key")
    client = create_started_client()

    response = client.get("/api/geospatial/sources/windy_webcams/credential-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["required"] is True
    assert payload["configured"] is False
    assert "environmentVariable" not in payload

###############################################################################
def test_geospatial_provider_account_setup_detail_reports_encrypted_storage(
    monkeypatch,
) -> None:
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    client = create_started_client()

    response = client.get("/api/geospatial/providers/tomtom/account-setup")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "tomtom"
    assert payload["requires_credentials"] is True
    assert "environment_variable" not in payload
    assert payload["configured"] is False
    assert payload["instructions"]
    assert any("encrypted Access settings" in item for item in payload["instructions"])

###############################################################################
@pytest.mark.parametrize("provider_id", ["opentripmap", "openchargemap"])
def test_optional_provider_credential_status_uses_saved_storage_only(
    monkeypatch, provider_id: str
) -> None:
    client = create_started_client()

    missing = client.get(f"/api/geospatial/sources/{provider_id}/credential-status")
    assert missing.status_code == 200
    assert "environmentVariable" not in missing.json()
    assert missing.json()["configured"] is False

    monkeypatch.setenv("AEGIS_UNUSED_PROVIDER_KEY", "test-key")
    configured = client.get(f"/api/geospatial/sources/{provider_id}/credential-status")
    assert configured.status_code == 200
    assert configured.json()["configured"] is False

###############################################################################
def test_account_setup_lists_all_credential_gated_manifest_providers() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    provider_ids = {item["provider_id"] for item in response.json()["providers"]}
    assert provider_ids == {
        "arcgis",
        "google_maps",
        "nasa_firms",
        "openaq",
        "openchargemap",
        "opentripmap",
        "tomtom",
        "windy_webcams",
    }

###############################################################################
def test_account_setup_includes_experimental_automation_support() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    supported = {"manual_only", "guided_playwright", "agent_assisted", "unsupported"}
    for item in response.json()["providers"]:
        assert item["automation"]["support"] in supported
        assert item["automation"]["experimental"] is True
        assert item["automation"]["experimental_label"] == "Experimental guided setup"

###############################################################################
def test_google_maps_is_manual_only_and_billing_aware() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    google_maps = next(
        item
        for item in response.json()["providers"]
        if item["provider_id"] == "google_maps"
    )
    assert google_maps["automation"]["support"] == "manual_only"
    assert any(
        "billing" in note.lower() for note in google_maps["automation"]["safety_notes"]
    )

###############################################################################
def test_opentripmap_is_unsupported() -> None:
    client = create_started_client()

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    opentripmap = next(
        item
        for item in response.json()["providers"]
        if item["provider_id"] == "opentripmap"
    )
    assert opentripmap["automation"]["support"] == "unsupported"

###############################################################################
def test_account_setup_response_excludes_secret_values(monkeypatch) -> None:
    monkeypatch.setenv("TOMTOM_API_KEY", "secret-tomtom-value")
    client = create_started_client()

    response = client.get("/api/geospatial/providers/account-setup")

    assert response.status_code == 200
    assert "secret-tomtom-value" not in str(response.json())

###############################################################################
def test_geospatial_audit_endpoint_passes() -> None:
    client = create_started_client()

    response = client.post("/api/geospatial/audit")

    assert response.status_code == 200
    assert response.json()["error_count"] == 0

###############################################################################
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_detail"),
    [
        (
            GeospatialCapabilityNotFoundError("missing capability"),
            404,
            "missing capability",
        ),
        (
            GeospatialInvalidRequestError("invalid request"),
            400,
            "invalid request",
        ),
        (
            GeospatialUnsupportedTileError("unsupported tile"),
            404,
            "unsupported tile",
        ),
        (
            GeospatialTileCredentialError("missing credential"),
            401,
            "missing credential",
        ),
        (
            GeospatialTileRequestError("provider failed"),
            502,
            "provider failed",
        ),
    ],
)
def test_raise_service_http_error_maps_expected_statuses(
    error: GeospatialApiServiceError,
    expected_status: int,
    expected_detail: str,
) -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_service_http_error(error)

    assert exc_info.value.status_code == expected_status
    assert exc_info.value.detail == expected_detail

###############################################################################
def test_raise_service_http_error_uses_generic_fallback_for_unknown_error() -> None:
    with pytest.raises(HTTPException) as exc_info:
        raise_service_http_error(GeospatialApiServiceError("internal failure"))

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Geospatial service request failed."
