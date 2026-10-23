from __future__ import annotations
from server.services.geospatial.inspection import MapInspectionService
import base64
import time
import pytest
from server.services.geospatial.render_capture import MAX_CAPTURE_BASE64_CHARS, RenderCapture, RenderCaptureStore
from datetime import UTC, datetime
from tests.conftest import run_async_in_thread
from server.contracts.geospatial import GeospatialLayerRenderDescriptor, GeospatialProviderLayerDescriptor, LocationSearchRequest, ViewportPolicy
from server.domain.agent.decision import ResolvedLocation
from server.domain.geospatial.providers import ProviderResponse
from server.services.geospatial.capability_registry import CapabilityRegistry
from server.services.geospatial.provider_registry import ProviderRegistry
from server.services.geospatial.render_descriptors import RenderDescriptorService
from server.services.geospatial.providers.base import ProviderAuthError

# --- test_map_inspection.py ---


###############################################################################
def test_feature_metadata_is_bounded_and_allowlisted() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "weather-points",
            "label": "Weather stations",
            "provider": "official-feed",
            "rendering_mode": "geojson",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "station-1",
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [8.54, 47.37]},
                        "properties": {
                            "name": "Zurich",
                            "metric": "temperature",
                            "value": 21.5,
                            "unit": "C",
                            "secret": {"not": "a scalar"},
                            "long_note": "x" * 500,
                        },
                    }
                ],
            },
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "feature"
    assert inspection.feature_id == "station-1"
    assert {field.key for field in inspection.fields} == {
        "name",
        "metric",
        "value",
        "unit",
    }
    assert all(
        len(str(field.value)) <= MapInspectionService.MAX_TEXT
        for field in inspection.fields
    )

###############################################################################
def test_feature_provenance_links_are_exposed_as_approved_source() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "gbif-species-occurrences",
            "label": "GBIF occurrences",
            "provider": "gbif",
            "rendering_mode": "clustered-points",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "123",
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [8.8, 46.2]},
                        "properties": {
                            "name": "Lynx lynx",
                            "basisOfRecord": "HUMAN_OBSERVATION",
                            "datasetKey": "dataset-1",
                            "datasetTitle": "Alpine observations",
                            "occurrenceUrl": "https://www.gbif.org/occurrence/123",
                            "datasetUrl": "https://www.gbif.org/dataset/dataset-1",
                        },
                    }
                ],
            },
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.source_url == "https://www.gbif.org/occurrence/123"
    assert {field.key for field in inspection.fields} >= {
        "name",
        "basisOfRecord",
        "datasetKey",
        "datasetTitle",
    }

###############################################################################
def test_location_metadata_gets_point_association() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "camera-1",
            "label": "Camera 1",
            "provider": "traffic-feed",
            "inspection_metadata": {
                "name": "Zurich camera",
                "status": "online",
                "latitude": 47.3769,
                "longitude": 8.5417,
                "official_url": "https://example.test/camera/1",
            },
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "location"
    assert inspection.geometry == {"type": "Point", "coordinates": [8.5417, 47.3769]}
    assert inspection.source_url == "https://example.test/camera/1"

###############################################################################
def test_raster_metadata_is_overlay_level_and_rejects_unsafe_links() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "rain-radar",
            "label": "Rain radar",
            "provider": "weather-feed",
            "rendering_mode": "raster-tile",
            "time": "2026-08-27T10:00:00Z",
            "units": "mm/h",
            "freshness": "updated 5 minutes ago",
            "source_url": "javascript:alert(1)",
            "warnings": ["Values are not available per raster cell."],
            "stale": True,
        }
    )

    assert len(inspections) == 1
    inspection = inspections[0]
    assert inspection.association == "overlay"
    assert inspection.stale is True
    assert inspection.source_url is None
    assert any(field.key == "units" for field in inspection.fields)
    assert inspection.warnings == ["Values are not available per raster cell."]

###############################################################################
def test_non_spatial_dataset_metadata_remains_inspectable() -> None:
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "population",
            "label": "Population dataset",
            "provider": "statistics",
            "metadata": {
                "metric": "population",
                "period": "2025",
                "geography": "Switzerland",
                "source": "Federal Statistical Office",
                "license": "CC BY",
                "update_time": "2026-01-01",
            },
        }
    )

    assert len(inspections) == 1
    assert inspections[0].association == "non_spatial"
    assert {field.key for field in inspections[0].fields} == {
        "metric",
        "period",
        "geography",
        "source",
        "license",
        "update_time",
    }

###############################################################################
def test_weather_feature_inspection_exposes_bounded_measurements_and_provenance() -> (
    None
):
    inspections = MapInspectionService.build_for_descriptor(
        {
            "id": "openmeteo_pressure_humidity_wind",
            "label": "Open-Meteo Pressure Humidity Wind",
            "provider": "openmeteo",
            "rendering_mode": "clustered-points",
            "data": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "id": "sanremo",
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [7.777, 43.817],
                        },
                        "properties": {
                            "name": "Sanremo",
                            "relative_humidity_2m": 62,
                            "surface_pressure": 1012,
                            "wind_speed_10m": 4.5,
                            "forecast_time": "2026-09-02T10:00",
                            "fetched_at": "2026-09-02T09:00:00+00:00",
                            "result_status": "ok",
                            "source_url": "https://api.open-meteo.com/v1/forecast",
                            "units": {
                                "relative_humidity_2m": "%",
                                "surface_pressure": "hPa",
                                "wind_speed_10m": "km/h",
                            },
                        },
                    }
                ],
            },
        }
    )

    assert len(inspections) == 1
    fields = {field.key: field for field in inspections[0].fields}
    assert fields["relative_humidity_2m"].value == 62
    assert fields["relative_humidity_2m"].unit == "%"
    assert fields["surface_pressure"].unit == "hPa"
    assert fields["wind_speed_10m"].unit == "km/h"
    assert inspections[0].source_url == "https://api.open-meteo.com/v1/forecast"

# --- test_render_capture_store.py ---




###############################################################################
def _png_base64() -> str:
    # Minimal 1x1 PNG payload.
    return base64.b64encode(
        bytes.fromhex(
            "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
            "1f15c4890000000d49444154789c626001000000ffff03000006000557"
            "bfabd40000000049454e44ae426082"
        )
    ).decode("ascii")

###############################################################################
def test_save_and_get_round_trips_by_run_identity() -> None:
    store = RenderCaptureStore()
    capture = store.save(
        run_id="run-1",
        map_session_id="map-1",
        collection_revision=2,
        mime_type="image/jpeg",
        image_base64=_png_base64(),
        width=640,
        height=480,
        viewport_bounds=[-73.0, 40.0, -72.0, 41.0],
    )

    assert isinstance(capture, RenderCapture)
    assert capture.run_id == "run-1"
    assert capture.collection_revision == 2
    assert capture.viewport_bounds == (-73.0, 40.0, -72.0, 41.0)

    found = store.get("run-1", "map-1", 2)
    assert found is not None
    assert found.image_base64 == _png_base64()
    assert len(store) == 1

    assert store.get("run-1", "map-1", 3) is None
    assert store.get("run-2", "map-1", 2) is None

###############################################################################
def test_save_rejects_invalid_mime_size_base64_and_identity() -> None:
    store = RenderCaptureStore()
    payload = _png_base64()
    with pytest.raises(ValueError, match="mime"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/gif",
            image_base64=payload,
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="base64"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64="not-base64!!",
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="size"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64="A" * (MAX_CAPTURE_BASE64_CHARS + 1),
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="run_id"):
        store.save(
            run_id="",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64=payload,
            width=10,
            height=10,
        )
    with pytest.raises(ValueError, match="width"):
        store.save(
            run_id="run-1",
            map_session_id="map-1",
            collection_revision=1,
            mime_type="image/jpeg",
            image_base64=payload,
            width=0,
            height=10,
        )

###############################################################################
def test_delete_for_run_removes_all_captures_for_that_run() -> None:
    store = RenderCaptureStore()
    payload = _png_base64()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    store.save(run_id="run-1", map_session_id="map-2", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    store.save(run_id="run-2", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)

    assert store.delete_for_run("run-1") == 2
    assert len(store) == 1
    assert store.get("run-1", "map-1", 1) is None
    assert store.get("run-2", "map-1", 1) is not None

###############################################################################
def test_ttl_expiry_reclaims_stale_captures() -> None:
    store = RenderCaptureStore(ttl_seconds=1.0)
    payload = _png_base64()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=payload, width=10, height=10)
    assert store.get("run-1", "map-1", 1) is not None

    # A capture recorded beyond the TTL is reclaimed on read.
    stale = RenderCaptureStore(ttl_seconds=1.0)
    stale._captures[("run-1", "map-1", 1)] = RenderCapture(
        run_id="run-1",
        map_session_id="map-1",
        collection_revision=1,
        mime_type="image/jpeg",
        image_base64=payload,
        width=10,
        height=10,
        viewport_bounds=None,
        captured_at=time.time() - 60.0,
    )
    assert stale.get("run-1", "map-1", 1) is None
    assert len(stale) == 0

###############################################################################
def test_clear_empties_the_store() -> None:
    store = RenderCaptureStore()
    store.save(run_id="run-1", map_session_id="map-1", collection_revision=1, mime_type="image/jpeg", image_base64=_png_base64(), width=10, height=10)
    store.bind_map_view("run-1", {"zoom": 5})
    store.clear()
    assert len(store) == 0
    assert store.map_view_for_run("run-1") is None

###############################################################################
def test_viewport_expiry_reclaims_unread_runs(monkeypatch) -> None:
    store = RenderCaptureStore(ttl_seconds=1.0)
    monkeypatch.setattr(time, "time", lambda: 100.0)
    store.bind_map_view("old-run", {"zoom": 5})
    monkeypatch.setattr(time, "time", lambda: 102.0)
    store.bind_map_view("new-run", {"zoom": 6})
    assert "old-run" not in store._map_views
    assert store.map_view_for_run("new-run") == {"zoom": 6}

###############################################################################
def test_user_attachment_binds_once_to_a_run_of_its_conversation() -> None:
    store = RenderCaptureStore()
    attachment_id = store.save_attachment(
        conversation_id="conv-1", mime_type="image/png", image_base64=_png_base64(), width=1, height=1
    )
    assert not store.has_attachment(attachment_id, "conv-2")
    assert not store.bind_attachment(attachment_id, "conv-2", "run-1")
    assert store.bind_attachment(attachment_id, "conv-1", "run-1")
    assert not store.bind_attachment(attachment_id, "conv-1", "run-2")
    attachment = store.attachment_for_run("run-1")
    assert attachment is not None and attachment.mime_type == "image/png"
    store.delete_for_run("run-1")
    assert store.attachment_for_run("run-1") is None

# --- test_render_descriptors.py ---





###############################################################################
class _CapabilityRegistry:

    # -------------------------------------------------------------------------
    def __init__(self, capability: dict) -> None:
        self.capability = capability

    # -------------------------------------------------------------------------
    def get_capability(self, capability_id: str) -> dict | None:
        return self.capability if self.capability["id"] == capability_id else None

###############################################################################
def test_openaq_auth_failure_cannot_be_a_deferred_success(monkeypatch) -> None:
    registry = ProviderRegistry()

    async def unavailable(*args, **kwargs):
        raise ProviderAuthError("OpenAQ API key is required.")

    monkeypatch.setattr(registry, "fetch", unavailable)
    with pytest.raises(ProviderAuthError, match="Configure them in Settings under Geospatial Access"):
        run_async_in_thread(
            RenderDescriptorService(
                provider_registry=registry
            ).build_overlay_descriptor("openaq_air_quality", request=_request())
        )

###############################################################################
def _request():
    location = ResolvedLocation(
        label="Rome", latitude=41.9, longitude=12.5, confidence=1.0
    )
    return LocationSearchRequest(
        resolved_location=location,
        action_id="map_search",
        basemap_id="osm_default",
        overlay_ids=["test-layer"],
        viewport=ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=25_000,
        ),
    )

###############################################################################
def _sanremo_request():
    location = ResolvedLocation(
        label="Sanremo", latitude=43.817, longitude=7.777, confidence=1.0
    )
    return LocationSearchRequest(
        resolved_location=location,
        action_id="map_search",
        basemap_id="osm_default",
        overlay_ids=["openmeteo_pressure_humidity_wind"],
        viewport=ViewportPolicy(
            center_latitude=location.latitude,
            center_longitude=location.longitude,
            radius_m=25_000,
        ),
    )

###############################################################################
class _SanremoWeatherProvider:
    provider_id = "openmeteo"

    # -------------------------------------------------------------------------
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
@pytest.mark.parametrize(
    ("overlay_id", "expected_host"),
    [
        ("noaa_radar", "opengeo.ncep.noaa.gov"),
        ("fema_nfhl_flood_zones", "hazards.fema.gov"),
    ],
)
def test_catalog_raster_overlays_expose_provider_tile_templates(
    overlay_id: str, expected_host: str
) -> None:
    service = RenderDescriptorService(capability_registry=CapabilityRegistry())

    result = run_async_in_thread(
        service.build_overlay_descriptor(overlay_id, request=_request())
    )

    assert result is not None
    descriptor, warnings = result
    assert warnings == []
    assert descriptor["rendering_mode"] == "raster-tile"
    tile_url_template = str(descriptor["tile_url_template"])
    if overlay_id in {"fema_nfhl_flood_zones", "noaa_radar"}:
        assert tile_url_template == (
            f"/api/geospatial/tiles/{overlay_id}/{{z}}/{{x}}/{{y}}.png"
        )
        assert expected_host in str(descriptor["source_url"])
    else:
        assert expected_host in tile_url_template
        assert "{bbox-epsg-3857}" in tile_url_template
    assert descriptor["render"]["tile_url_template"] == tile_url_template

###############################################################################
@pytest.mark.parametrize(
    ("overlay_id", "expected_host", "expected_protocol"),
    [
        ("esa_worldcover", "mapproxy.terrascope.be", "wms"),
        ("eea_noise_end2022", "noise.discomap.eea.europa.eu", "wms"),
        ("IMERG_Precipitation_Rate", "gibs.earthdata.nasa.gov", "wms"),
    ],
)
def test_catalog_public_raster_descriptors_use_backend_proxy(
    overlay_id: str, expected_host: str, expected_protocol: str
) -> None:
    service = RenderDescriptorService(capability_registry=CapabilityRegistry())

    result = run_async_in_thread(
        service.build_overlay_descriptor(overlay_id, request=_request())
    )

    assert result is not None
    descriptor, warnings = result
    assert warnings == []
    expected_template = f"/api/geospatial/tiles/{overlay_id}/{{z}}/{{x}}/{{y}}.png"
    assert descriptor["tile_url_template"] == expected_template
    assert expected_host in str(descriptor["source_url"])
    assert descriptor["source_protocol"].lower() == expected_protocol
    assert descriptor["attribution"]
    if overlay_id == "esa_worldcover":
        assert descriptor["layer_id"] == "esa-worldcover-map-10m-2021-v2_map"
        render = descriptor["render"]
        assert isinstance(render, dict)
        assert render["rendering_mode"] == "wms"
        assert render["source_protocol"] == "wms"
        assert render["layer_id"] == "esa-worldcover-map-10m-2021-v2_map"
        assert render["crs"] == "EPSG:3857"
        assert render["format"] == "image/png"
        assert render["default_time"] is None
        assert render["attribution"] == ["© ESA WorldCover / Terrascope"]
        assert descriptor["url"] == (
            "/api/geospatial/tiles/esa_worldcover/{z}/{x}/{y}.png"
        )

###############################################################################
class _GibsProvider:
    provider_id = "gibs"

    # -------------------------------------------------------------------------
    async def describe_layer(self, layer_id: str, *, refresh: bool = False):
        del refresh
        assert layer_id == "MODIS_Terra_NDVI_8Day"
        return GeospatialProviderLayerDescriptor(
            provider="gibs",
            layer_id=layer_id,
            title="MODIS Terra NDVI 8-Day",
            rendering_mode="wmts",
            source_protocol="wmts",
            data_format="image/png",
            geometry_type="raster-grid",
            default_time="2026-09-28",
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
                default_time="2026-09-28",
                attribution=["© NASA GIBS"],
            ),
            attribution=["© NASA GIBS"],
        )

###############################################################################
def test_provider_discovered_gibs_raster_descriptor_uses_proxy_and_keeps_time() -> None:
    service = RenderDescriptorService(
        provider_registry=ProviderRegistry(
            providers=[_GibsProvider()]  # type: ignore[list-item]
        )
    )

    descriptor, warnings = run_async_in_thread(
        service.build_provider_layer_overlay(
            provider_id="gibs",
            layer_id="MODIS_Terra_NDVI_8Day",
            request=_request(),
        )
    )

    assert warnings == []
    assert descriptor["url"] == (
        "/api/geospatial/tiles/gibs:MODIS_Terra_NDVI_8Day/"
        "{z}/{x}/{y}.png?time={time}"
    )
    assert descriptor["source_url"] == (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best"
    )
    assert descriptor["default_time"] == "2026-09-28"
    assert descriptor["render"]["tile_url_template"] == descriptor["url"]

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
                    "url": "/api/geospatial/tiles/rainviewer_precipitation_radar/{z}/{x}/{y}.png",
                    "default_opacity": 0.7,
                        "fit_max_zoom": 6,
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
    assert descriptor["fit_max_zoom"] == 6
    assert descriptor["tile_url_template"] == (
        "/api/geospatial/tiles/rainviewer_precipitation_radar/{z}/{x}/{y}.png"
    )

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
