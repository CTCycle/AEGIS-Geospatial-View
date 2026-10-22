from __future__ import annotations
from datetime import UTC, datetime
import pytest
import asyncio
from tests.conftest import run_async_in_thread
from server.domain.geospatial.providers import ProviderRequest
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.base import ProviderUnavailableError
from typing import Any
from server.services.geospatial.rainviewer import RainViewerRequestError, RainViewerService
from server.services.geospatial.providers.rainviewer import RainViewerProvider

# --- test_nasa_gibs_provider.py ---




WMTS_XML = """<?xml version="1.0"?>
<Capabilities xmlns="http://www.opengis.net/wmts/1.0" xmlns:ows="http://www.opengis.net/ows/1.1">
  <Contents>
    <Layer>
      <ows:Title>MODIS Terra NDVI 8-Day</ows:Title>
      <ows:Abstract>Vegetation index.</ows:Abstract>
      <ows:Identifier>MODIS_Terra_NDVI_8Day</ows:Identifier>
      <Style isDefault="true"><ows:Identifier>default</ows:Identifier></Style>
      <Format>image/png</Format>
      <Dimension>
        <ows:Identifier>Time</ows:Identifier>
        <Default>2026-06-18</Default>
        <Value>2026-06-10/2026-06-18/P8D</Value>
      </Dimension>
      <TileMatrixSetLink><TileMatrixSet>GoogleMapsCompatible_Level9</TileMatrixSet></TileMatrixSetLink>
    </Layer>
  </Contents>
</Capabilities>
"""

WMS_XML = """<?xml version="1.0"?>
<WMS_Capabilities xmlns="http://www.opengis.net/wms">
  <Capability>
    <Request><GetMap><Format>image/png</Format></GetMap></Request>
    <Layer>
      <Layer queryable="0">
        <Name>MODIS_Terra_NDVI_8Day</Name>
        <Title>MODIS Terra NDVI 8-Day WMS</Title>
        <CRS>EPSG:3857</CRS>
        <Style><Name>default</Name></Style>
        <Dimension name="time" default="2026-06-18">2026-06-10/2026-06-18/P8D</Dimension>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""

INCOMPATIBLE_WMTS_XML = WMTS_XML.replace(
    "GoogleMapsCompatible_Level9", "EPSG:4326"
)
VECTOR_ONLY_WMTS_XML = WMTS_XML.replace(
    "<Format>image/png</Format>",
    "<Format>application/vnd.mapbox-vector-tile</Format>",
)


###############################################################################
def _large_wms_xml() -> str:
    layers = "".join(
        f"""
        <Layer>
          <Name>{layer_id}</Name>
          <Title>{layer_id}</Title>
          <CRS>EPSG:3857</CRS>
          <Style><Name>default</Name></Style>
        </Layer>
        """
        for layer_id in [
            *(f"unrelated_{index}" for index in range(250)),
            "SRTM_Color_Index",
        ]
    )
    return f"""<?xml version="1.0"?>
    <WMS_Capabilities xmlns="http://www.opengis.net/wms">
      <Capability>
        <Request><GetMap><Format>image/png</Format></GetMap></Request>
        <Layer>{layers}</Layer>
      </Capability>
    </WMS_Capabilities>
    """

###############################################################################
async def _assert_nasa_gibs_provider_parses_xml_and_prefers_wmts() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return WMTS_XML if "wmts" in url else WMS_XML

    provider = NASAGIBSProvider(fetcher=fetcher)

    layers = await provider.list_layers(query="NDVI", limit=10)

    assert len(layers) == 1
    layer = layers[0]
    assert layer.layer_id == "MODIS_Terra_NDVI_8Day"
    assert layer.rendering_mode == "wmts"
    assert layer.source_protocol == "wmts"
    assert layer.default_time == "2026-06-18"
    assert layer.render is not None
    assert layer.render.tile_url_template is not None
    assert "GoogleMapsCompatible_Level9" in layer.render.tile_url_template
    assert "{time}" in layer.render.tile_url_template
    assert "/{z}/{y}/{x}.png" in layer.render.tile_url_template

###############################################################################
async def _assert_nasa_gibs_provider_describes_one_layer() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return WMTS_XML if "wmts" in url else WMS_XML

    provider = NASAGIBSProvider(fetcher=fetcher)

    layer = await provider.describe_layer("MODIS_Terra_NDVI_8Day")

    assert layer.title == "MODIS Terra NDVI 8-Day"
    assert "EPSG:3857" in layer.crs

###############################################################################
def test_nasa_gibs_provider_parses_xml_and_prefers_wmts() -> None:
    run_async_in_thread(_assert_nasa_gibs_provider_parses_xml_and_prefers_wmts())

###############################################################################
def test_nasa_gibs_provider_uses_the_advertised_wmts_zoom_ceiling() -> None:
    level_six_xml = WMTS_XML.replace(
        "GoogleMapsCompatible_Level9", "GoogleMapsCompatible_Level6"
    )

    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return level_six_xml if "wmts" in url else WMS_XML

    layer = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).describe_layer(
            "MODIS_Terra_NDVI_8Day"
        )
    )

    assert layer.render is not None
    assert layer.render.tile_matrix_set == "GoogleMapsCompatible_Level6"
    assert layer.render.min_zoom == 0
    assert layer.render.max_zoom == 6

###############################################################################
def test_nasa_gibs_provider_describes_one_layer() -> None:
    run_async_in_thread(_assert_nasa_gibs_provider_describes_one_layer())

###############################################################################
def test_nasa_gibs_provider_returns_renderable_raster_result() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return WMTS_XML if "wmts" in url else WMS_XML

    response = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="MODIS_Terra_NDVI_8Day",
                params={"layer_id": "MODIS_Terra_NDVI_8Day"},
            )
        )
    )

    assert response.result_type == "raster"
    assert response.payload["render"] is not None

###############################################################################
def test_nasa_gibs_provider_maps_stable_capability_to_manifest_layer() -> None:
    native_wmts = VECTOR_ONLY_WMTS_XML.replace(
        "MODIS_Terra_NDVI_8Day", "MODIS_Combined_Thermal_Anomalies_All"
    )
    native_wms = WMS_XML.replace(
        "MODIS_Terra_NDVI_8Day", "MODIS_Combined_Thermal_Anomalies_All"
    )

    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return native_wmts if "wmts" in url else native_wms

    response = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="MODIS_Combined_Thermal_Anomalies_Fire",
                params={
                    "metadata": {
                        "layer_id": "MODIS_Combined_Thermal_Anomalies_All"
                    }
                },
            )
        )
    )

    assert response.capability_id == "MODIS_Combined_Thermal_Anomalies_Fire"
    assert response.payload["layer"]["layer_id"] == (
        "MODIS_Combined_Thermal_Anomalies_All"
    )
    assert response.payload["render"] is not None
    assert response.payload["render"]["rendering_mode"] == "wms"

###############################################################################
def test_nasa_gibs_provider_falls_back_to_wms_without_web_mercator_wmts() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return INCOMPATIBLE_WMTS_XML if "wmts" in url else WMS_XML

    layer = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).describe_layer("MODIS_Terra_NDVI_8Day")
    )

    assert layer.render is not None
    assert layer.render.rendering_mode == "wms"
    assert layer.render.source_protocol == "wms"
    assert layer.default_time == "2026-06-18"

###############################################################################
def test_nasa_gibs_provider_prefers_wms_when_wmts_is_vector_only() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return VECTOR_ONLY_WMTS_XML if "wmts" in url else WMS_XML

    layer = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).describe_layer(
            "MODIS_Terra_NDVI_8Day"
        )
    )

    assert layer.render is not None
    assert layer.render.rendering_mode == "wms"
    assert layer.render.source_protocol == "wms"
    assert layer.render.url == (
        "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
    )

###############################################################################
def test_nasa_gibs_provider_falls_back_to_wms_when_wmts_discovery_is_unavailable() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        if "wmts" in url:
            raise ProviderUnavailableError("WMTS capabilities timed out")
        return WMS_XML

    layer = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).describe_layer(
            "MODIS_Terra_NDVI_8Day"
        )
    )

    assert layer.render is not None
    assert layer.render.rendering_mode == "wms"
    assert layer.render.source_protocol == "wms"
    assert layer.layer_id == "MODIS_Terra_NDVI_8Day"

###############################################################################
def test_nasa_gibs_provider_describes_named_layer_beyond_catalog_page_ceiling() -> None:
    large_wms_xml = _large_wms_xml()

    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return (
            "<Capabilities xmlns=\"http://www.opengis.net/wmts/1.0\"><Contents />"
            "</Capabilities>"
            if "wmts" in url
            else large_wms_xml
        )

    layer = run_async_in_thread(
        NASAGIBSProvider(fetcher=fetcher).describe_layer("SRTM_Color_Index")
    )

    assert layer.layer_id == "SRTM_Color_Index"
    assert layer.render is not None
    assert layer.render.rendering_mode == "wms"

###############################################################################
def test_nasa_gibs_provider_preserves_default_and_explicit_requested_time() -> None:
    async def fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return WMTS_XML if "wmts" in url else WMS_XML

    provider = NASAGIBSProvider(fetcher=fetcher)
    response = run_async_in_thread(
        provider.fetch(
            ProviderRequest(
                capability_id="MODIS_Terra_NDVI_8Day",
                params={"layer_id": "MODIS_Terra_NDVI_8Day"},
                time=datetime(2026, 6, 20, tzinfo=UTC),
            )
        )
    )

    assert response.payload["render"]["default_time"] == "2026-06-18"
    assert response.payload["render"]["time"] == "2026-06-20"
    assert "{time}" in response.payload["render"]["tile_url_template"]

###############################################################################
def test_nasa_gibs_provider_rejects_missing_layer_and_malformed_capabilities() -> None:
    async def malformed_fetcher(url: str, headers: dict[str, str] | None) -> str:
        del url, headers
        return "<not-valid-xml"

    with pytest.raises(ProviderUnavailableError, match="malformed XML"):
        run_async_in_thread(
            NASAGIBSProvider(fetcher=malformed_fetcher).list_layers()
        )

    async def valid_fetcher(url: str, headers: dict[str, str] | None) -> str:
        del headers
        return WMTS_XML if "wmts" in url else WMS_XML

    with pytest.raises(ProviderUnavailableError, match="was not found"):
        run_async_in_thread(
            NASAGIBSProvider(fetcher=valid_fetcher).describe_layer("missing-layer")
        )

# --- test_rainviewer_recent_history.py ---




###############################################################################
def test_rainviewer_ignores_discontinued_nowcast_frames() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": 100, "path": "/v2/radar/100"},
                    {"time": 200, "path": "/v2/radar/200"},
                ],
                "nowcast": [
                    {"time": 999, "path": "/v2/radar/999"},
                ],
            },
        }

    service = RainViewerService(
        metadata_url="https://example.test/weather-maps.json",
        user_agent="AEGIS-Test/1.0",
        timeout_s=1.0,
        cache_ttl_s=30.0,
        min_call_interval_s=0.05,
        fetcher=fetcher,
    )

    result = asyncio.run(service.get_latest_radar_metadata())

    assert result["kind"] == "recent_precipitation_radar"
    assert result["latest_time"] == 200
    assert result["history_start_time"] == 100
    assert result["history_end_time"] == 200
    assert result["frame_count"] == 2
    assert result["max_zoom"] == 7
    assert "/v2/radar/200/256/" in result["tile_url_template"]
    assert "/v2/radar/999/" not in result["tile_url_template"]

###############################################################################
def test_rainviewer_filters_malformed_past_timestamps() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": "not-a-timestamp", "path": "/v2/radar/bad"},
                    {"time": None, "path": "/v2/radar/missing"},
                    {"time": 300, "path": "/v2/radar/300"},
                ]
            }
        }

    service = RainViewerService(fetcher=fetcher)

    result = asyncio.run(service.get_latest_radar_metadata())

    assert result["latest_time"] == 300
    assert result["frame_count"] == 1
    assert result["history_start_time"] == 300

###############################################################################
def test_rainviewer_rejects_when_no_past_frame_has_a_valid_timestamp() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "radar": {
                "past": [
                    {"time": "invalid", "path": "/v2/radar/invalid"},
                    {"time": 0, "path": "/v2/radar/zero"},
                ]
            }
        }

    service = RainViewerService(fetcher=fetcher)

    try:
        asyncio.run(service.get_latest_radar_metadata())
    except RainViewerRequestError as exc:
        assert "recent radar history frames" in str(exc)
    else:
        raise AssertionError("RainViewerRequestError was not raised.")

###############################################################################
@pytest.mark.parametrize(
    "host",
    [
        "http://tilecache.rainviewer.com",
        "https://evil.example",
        "https://tilecache.rainviewer.com:443",
        "https://user:password@tilecache.rainviewer.com",
    ],
)
def test_rainviewer_rejects_untrusted_metadata_hosts(host: str) -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": host,
            "radar": {"past": [{"time": 100, "path": "/v2/radar/100"}]},
        }

    with pytest.raises(RainViewerRequestError, match="host"):
        asyncio.run(RainViewerService(fetcher=fetcher).get_latest_radar_metadata())


###############################################################################
def test_rainviewer_ignores_invalid_frame_paths_and_keeps_latest_safe_frame() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {
                "past": [
                    {"time": 300, "path": "https://evil.example/v2/radar/300"},
                    {"time": 200, "path": "/v2/radar/200"},
                ]
            },
        }

    result = asyncio.run(RainViewerService(fetcher=fetcher).get_latest_radar_metadata())

    assert result["latest_time"] == 200
    assert result["tile_url_template"].startswith(
        "https://tilecache.rainviewer.com/v2/radar/200/256/"
    )


###############################################################################
def test_rainviewer_forces_universal_blue_color_scheme() -> None:
    async def fetcher(_url: str, _headers: dict[str, str]) -> dict[str, Any]:
        return {
            "host": "https://tilecache.rainviewer.com",
            "radar": {"past": [{"time": 100, "path": "/v2/radar/100"}]},
        }

    result = asyncio.run(
        RainViewerService(fetcher=fetcher, tile_color_scheme=6).get_latest_radar_metadata()
    )

    assert "/2/1_1.png" in result["tile_url_template"]


###############################################################################
def test_rainviewer_provider_reports_server_bound_scope_evidence() -> None:

    ###############################################################################
    class _Service:

        # -------------------------------------------------------------------------
        async def get_latest_radar_metadata(self) -> dict[str, Any]:
            return {
                "tile_url_template": "https://tilecache.rainviewer.com/v2/radar/200/256/{z}/{x}/{y}/2/1_1.png",
                "latest_time": 200,
                "history_start_time": 100,
                "history_end_time": 200,
                "frame_count": 2,
                "max_zoom": 7,
                "resolved_at": "2026-09-30T00:00:00+00:00",
                "attribution": "© RainViewer",
            }

    response = asyncio.run(
        RainViewerProvider(service=_Service()).fetch(
            ProviderRequest(
                capability_id="rainviewer_precipitation_radar",
                params={
                    "latitude": 40.8358846,
                    "longitude": 14.2487679,
                    "temporal_mode": "current",
                },
            )
        )
    )

    assert response.coverage == {
        "spatial_scope_satisfied": True,
        "temporal_scope_satisfied": True,
    }
    assert response.observation_time == "1970-01-01T00:03:20+00:00"