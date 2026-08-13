from __future__ import annotations

from tests.conftest import run_async_in_thread
from server.services.geospatial.providers.nasa_gibs import NASAGIBSProvider

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
def test_nasa_gibs_provider_describes_one_layer() -> None:
    run_async_in_thread(_assert_nasa_gibs_provider_describes_one_layer())
