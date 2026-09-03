from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import run_async_in_thread

import pytest

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.domain.geospatial.providers import ProviderResponse
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.render_descriptors import RenderDescriptorService
from server.services.search.request_builder import RequestBuilder


###############################################################################
class _CapabilityRegistry:
    # -------------------------------------------------------------------------
    def __init__(self, capability: dict) -> None:
        self.capability = capability

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict | None:
        return self.capability if self.capability["id"] == capability_id else None


###############################################################################
def _request():
    return RequestBuilder().build_location_search_request(
        ExecutionPlan(
            state="map_search",
            action_id="map_search",
            basemap_id="osm_default",
            overlay_ids=["test-layer"],
        ),
        ResolvedLocation(
            label="Rome",
            latitude=41.9,
            longitude=12.5,
            confidence=1.0,
        ),
    )


def _sanremo_request():
    return RequestBuilder().build_location_search_request(
        ExecutionPlan(
            state="map_search",
            action_id="map_search",
            basemap_id="osm_default",
            overlay_ids=["openmeteo_pressure_humidity_wind"],
        ),
        ResolvedLocation(
            label="Sanremo",
            latitude=43.817,
            longitude=7.777,
            confidence=1.0,
        ),
    )


class _SanremoWeatherProvider:
    provider_id = "openmeteo"

    async def fetch(self, request):  # noqa: ANN001
        return ProviderResponse(
            capability_id=request.capability_id,
            provider_id=self.provider_id,
            payload={
                "features": [
                    {
                        "id": "sanremo-weather",
                        "name": "Sanremo",
                        "latitude": 43.817,
                        "longitude": 7.777,
                        "relative_humidity_2m": 68,
                        "surface_pressure": 1011,
                        "wind_speed_10m": 5.2,
                        "metadata": {
                            "forecastTime": "2026-09-02T10:00",
                        },
                    }
                ],
                "requested_variables": ["relative_humidity_2m"],
                "request_parameters": {"latitude": 43.817, "longitude": 7.777},
            },
            fetched_at=datetime(2026, 9, 2, 9, tzinfo=UTC),
            result_status="ok",
            result_type="features",
            observation_time="2026-09-02T09:00",
            units={
                "relative_humidity_2m": "%",
                "surface_pressure": "hPa",
                "wind_speed_10m": "km/h",
            },
            source_url="https://api.open-meteo.com/v1/forecast",
            warnings=["Provider warning"],
        )


###############################################################################
def test_provider_backed_sanremo_weather_descriptor_contains_renderable_data() -> None:
    capability = {
        "id": "openmeteo_pressure_humidity_wind",
        "name": "Open-Meteo Pressure Humidity Wind Forecast",
        "provider": "openmeteo",
        "type": "time-series-insight",
        "capabilityKind": "analysis-tool",
        "renderingMode": "clustered-points",
        "metadata": {
            "label": "Open-Meteo Pressure Humidity Wind",
            "render_backend": "provider",
            "url": "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}",
            "source_protocol": "JSON time series",
            "data_format": "JSON",
            "geometry_type": "point",
        },
    }
    service = RenderDescriptorService(
        capability_registry=_CapabilityRegistry(capability),  # type: ignore[arg-type]
        provider_registry=ProviderRegistry(
            providers=[_SanremoWeatherProvider()]  # type: ignore[list-item]
        ),
    )

    result = run_async_in_thread(
        service.build_overlay_descriptor(
            "openmeteo_pressure_humidity_wind", request=_sanremo_request()
        )
    )

    assert result is not None
    descriptor, warnings = result
    assert warnings == ["Provider warning"]
    assert descriptor["warnings"] == ["Provider warning"]
    assert descriptor["rendering_mode"] == "clustered-points"
    assert str(descriptor["url"]).startswith(
        "/api/geospatial/layers/openmeteo_pressure_humidity_wind/geojson?"
    )
    assert "api.open-meteo.com" not in str(descriptor["url"])
    assert descriptor["source_url"] == "https://api.open-meteo.com/v1/forecast"
    assert descriptor["result_status"] == "ok"
    feature = descriptor["data"]["features"][0]
    assert feature["geometry"]["coordinates"] == [7.777, 43.817]
    assert feature["properties"]["relative_humidity_2m"] == 68


###############################################################################
def test_render_descriptor_service_exposes_configurable_openfreemap_style(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENFREEMAP_STYLE_BASE_URL", "https://maps.internal.example")
    service = RenderDescriptorService(
        capability_registry=_CapabilityRegistry(
            {
                "id": "openfreemap_liberty",
                "name": "OpenFreeMap Liberty",
                "provider": "openfreemap",
                "metadata": {
                    "label": "OpenFreeMap Liberty",
                    "style_url": "https://tiles.openfreemap.org/styles/liberty",
                    "attribution": "OpenFreeMap",
                },
            }
        ),
    )

    result = run_async_in_thread(
        service.build_basemap_descriptor("openfreemap_liberty")
    )

    assert result is not None
    assert result["style_url"] == "https://maps.internal.example/styles/liberty"


###############################################################################
def test_render_descriptor_service_builds_complete_wms_template() -> None:
    template = RenderDescriptorService.build_wms_tile_template(
        url="https://example.test/wms",
        layer_id="layer",
        crs="EPSG:3857",
        image_format="image/png",
        style="default",
        time="2026-06-18",
        version="1.1.1",
        exceptions="application/vnd.ogc.se_inimage",
    )

    assert "service=WMS" in template
    assert "request=GetMap" in template
    assert "layers=layer" in template
    assert "srs=EPSG:3857" in template
    assert "bbox={bbox-epsg-3857}" in template
    assert "width=256" in template
    assert "height=256" in template
    assert "transparent=true" in template
    assert "time=2026-06-18" in template


###############################################################################
def test_render_descriptor_service_builds_complete_wmts_template() -> None:
    template = RenderDescriptorService.build_wmts_tile_template(
        url="https://example.test/wmts",
        layer_id="layer",
        style="default",
        image_format="image/png",
        tile_matrix_set="GoogleMapsCompatible_Level9",
        time="2026-06-18",
    )

    assert "service=WMTS" in template
    assert "request=GetTile" in template
    assert "layer=layer" in template
    assert "style=default" in template
    assert "tilematrixset=GoogleMapsCompatible_Level9" in template
    assert "tilematrix=GoogleMapsCompatible_Level9:{z}" in template
    assert "tilerow={y}" in template
    assert "tilecol={x}" in template
    assert "format=image/png" in template
    assert "time=2026-06-18" in template


###############################################################################
def test_render_descriptor_service_caps_rainviewer_at_supported_zoom() -> None:
    service = RenderDescriptorService(
        capability_registry=_CapabilityRegistry(
            {
                "id": "rainviewer_precipitation_radar",
                "name": "RainViewer Precipitation Radar",
                "provider": "rainviewer",
                "type": "tile",
                "capabilityKind": "raster-overlay",
                "renderingMode": "raster-tile",
                "metadata": {
                    "url": "https://tilecache.rainviewer.com/v2/radar/test/256/{z}/{x}/{y}/2/1_1.png",
                    "default_opacity": 0.7,
                },
            }
        ),
    )

    result = run_async_in_thread(
        service.build_overlay_descriptor(
            "rainviewer_precipitation_radar", request=_request()
        )
    )

    assert result is not None
    descriptor, _warnings = result
    assert descriptor["max_zoom"] == 7


###############################################################################
def test_census_demographic_render_uses_server_provider_endpoint() -> None:
    service = RenderDescriptorService(capability_registry=CapabilityRegistry())

    result = run_async_in_thread(
        service.build_overlay_descriptor(
            "census_tigerweb_demographics",
            request=_request(),
        )
    )

    assert result is not None
    descriptor, warnings = result
    assert str(descriptor["url"]).startswith(
        "/api/geospatial/layers/census_tigerweb_demographics/geojson?"
    )
    assert "live=true" in str(descriptor["url"])
    assert descriptor["rendering_mode"] == "choropleth"
    assert warnings == []


###############################################################################
@pytest.mark.parametrize(
    ("rendering_mode", "capability_kind", "capability_type", "metadata"),
    [
        (
            "xyz",
            "raster-overlay",
            "tile",
            {"url": "https://example.test/{z}/{x}/{y}.png"},
        ),
        (
            "raster-tile",
            "raster-overlay",
            "tile",
            {"url": "https://example.test/{z}/{x}/{y}.png"},
        ),
        (
            "wms",
            "raster-overlay",
            "wms",
            {"url": "https://example.test/wms", "layers": "x"},
        ),
        (
            "wmts",
            "raster-overlay",
            "wmts",
            {
                "url": "https://example.test/wmts",
                "layer_id": "x",
                "tile_matrix_set": "EPSG:3857",
            },
        ),
        ("geojson", "vector-overlay", "geojson", {}),
        ("clustered-points", "vector-overlay", "geojson", {}),
        ("choropleth", "vector-overlay", "geojson", {}),
        (
            "vector-tile",
            "vector-overlay",
            "vector-tile",
            {"url": "https://example.test/{z}/{x}/{y}.pbf", "layer_id": "x"},
        ),
        ("camera-points", "camera-network", "camera-network", {}),
        ("metadata-only", "analysis-tool", "time-series-insight", {}),
    ],
)
def test_overlay_descriptor_covers_every_declared_rendering_mode(
    rendering_mode: str,
    capability_kind: str,
    capability_type: str,
    metadata: dict,
) -> None:
    capability = {
        "id": "test-layer",
        "name": "Test layer",
        "provider": "test",
        "type": capability_type,
        "capabilityKind": capability_kind,
        "renderingMode": rendering_mode,
        "metadata": {
            "source_protocol": rendering_mode,
            "data_format": "GeoJSON"
            if rendering_mode
            in {
                "geojson",
                "clustered-points",
                "choropleth",
                "camera-points",
            }
            else "tile",
            "geometry_type": "Point"
            if rendering_mode
            in {
                "clustered-points",
                "camera-points",
            }
            else "Polygon",
            **metadata,
        },
    }
    service = RenderDescriptorService(
        capability_registry=_CapabilityRegistry(capability),  # type: ignore[arg-type]
    )

    result = run_async_in_thread(
        service.build_overlay_descriptor("test-layer", request=_request())
    )

    assert result is not None
    descriptor, warnings = result
    assert descriptor["rendering_mode"] == rendering_mode
    assert isinstance(warnings, list)
    if rendering_mode == "metadata-only":
        assert "url" not in descriptor
        assert "tile_url_template" not in descriptor
        assert "render" not in descriptor
    else:
        assert descriptor.get("url") or descriptor.get("render")
