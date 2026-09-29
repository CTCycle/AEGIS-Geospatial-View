from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.conftest import run_async_in_thread
from server.domain.geospatial.providers import ProviderRequest
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider
from server.services.geospatial.providers.base import ProviderUnavailableError

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
