from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date

import httpx
import pytest

from AEGIS.app.api.schemas.geographics import Coordinates, MapRequest, TemporalContext
from AEGIS.app.api.schemas.gibs import GIBSMapOptions, WMTSRequestOptions, WMSRequestOptions
from AEGIS.app.utils.services.geographics import GIBSClient, GIBSDiscovery, GIBSSettings


WMTS_CAPABILITIES_XML = """<?xml version=\"1.0\"?>
<Capabilities xmlns=\"http://www.opengis.net/wmts/1.0\" xmlns:ows=\"http://www.opengis.net/ows/1.1\">
  <Contents>
    <Layer>
      <ows:Title>Sample Layer</ows:Title>
      <ows:Identifier>Sample_Layer</ows:Identifier>
      <Style isDefault=\"true\">
        <ows:Identifier>default</ows:Identifier>
      </Style>
      <Format>image/png</Format>
      <Dimension>
        <ows:Identifier>Time</ows:Identifier>
        <Default>2024-01-10</Default>
        <Current>false</Current>
        <Value>2024-01-09</Value>
        <Value>2024-01-10</Value>
      </Dimension>
      <TileMatrixSetLink>
        <TileMatrixSet>GoogleMapsCompatible_Level2</TileMatrixSet>
      </TileMatrixSetLink>
    </Layer>
    <TileMatrixSet>
      <ows:Identifier>GoogleMapsCompatible_Level2</ows:Identifier>
      <ows:SupportedCRS>EPSG:3857</ows:SupportedCRS>
      <TileMatrix>
        <ows:Identifier>0</ows:Identifier>
        <ScaleDenominator>559082264.029</ScaleDenominator>
        <TopLeftCorner>-20037508.3427892 20037508.3427892</TopLeftCorner>
        <TileWidth>256</TileWidth>
        <TileHeight>256</TileHeight>
        <MatrixWidth>1</MatrixWidth>
        <MatrixHeight>1</MatrixHeight>
      </TileMatrix>
      <TileMatrix>
        <ows:Identifier>1</ows:Identifier>
        <ScaleDenominator>279541132.015</ScaleDenominator>
        <TopLeftCorner>-20037508.3427892 20037508.3427892</TopLeftCorner>
        <TileWidth>256</TileWidth>
        <TileHeight>256</TileHeight>
        <MatrixWidth>2</MatrixWidth>
        <MatrixHeight>2</MatrixHeight>
      </TileMatrix>
    </TileMatrixSet>
  </Contents>
</Capabilities>
"""


WMS_CAPABILITIES_130 = """<?xml version=\"1.0\"?>
<WMS_Capabilities version=\"1.3.0\">
  <Capability>
    <Request>
      <GetMap>
        <Format>image/png</Format>
        <Format>image/jpeg</Format>
      </GetMap>
    </Request>
    <Layer>
      <Layer>
        <Name>Sample_Layer</Name>
        <Title>Sample Layer</Title>
        <CRS>EPSG:4326</CRS>
        <Style>
          <Name>default</Name>
        </Style>
        <Dimension name=\"time\" default=\"2024-01-10\" nearestValue=\"1\">2024-01-09,2024-01-10</Dimension>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
"""


WMS_CAPABILITIES_111 = """<?xml version=\"1.0\"?>
<WMT_MS_Capabilities version=\"1.1.1\">
  <Capability>
    <Request>
      <GetMap>
        <Format>image/png</Format>
      </GetMap>
    </Request>
    <Layer>
      <Layer>
        <Name>Sample_Layer</Name>
        <Title>Sample Layer</Title>
        <SRS>EPSG:3857</SRS>
        <Style>
          <Name>default</Name>
        </Style>
        <Extent name=\"time\" default=\"2024-01-10\">2024-01-08,2024-01-09,2024-01-10</Extent>
      </Layer>
    </Layer>
  </Capability>
</WMT_MS_Capabilities>
"""


WMTS_DESCRIBE_DOMAIN = """<?xml version=\"1.0\"?>
<DescribeDomainResponse>
  <DomainValues>
    <DimensionDomain>
      <DefaultValue>2024-01-10</DefaultValue>
      <Value>2024-01-08</Value>
      <Value>2024-01-09</Value>
      <Value>2024-01-10</Value>
    </DimensionDomain>
  </DomainValues>
</DescribeDomainResponse>
"""


def build_coordinates_request(map_options: GIBSMapOptions) -> MapRequest:
    return MapRequest(
        filter=None,
        mode="coordinates",
        coordinates=Coordinates(latitude=34.0, longitude=-118.2),
        location=None,
        temporal=TemporalContext(
            reference_date=date(2024, 1, 10),
            time_of_day=None,
            timeline_year=2024,
        ),
        map_options=map_options,
    )


def configure_client(monkeypatch: pytest.MonkeyPatch, handler: Callable[[str], str]) -> GIBSClient:
    settings = GIBSSettings(enable_domain_sharding=False, shard_domains=["gibs.earthdata.nasa.gov"])
    client = GIBSClient(settings=settings)

    def patched_http_get(self: GIBSDiscovery, url: str) -> str:
        return handler(url)

    monkeypatch.setattr(GIBSDiscovery, "_http_get", patched_http_get)
    return client


def test_wmts_payload_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    def http_handler(url: str) -> str:
        if "WMTSCapabilities.xml" in url:
            return WMTS_CAPABILITIES_XML
        raise AssertionError(f"Unexpected WMTS URL: {url}")

    client = configure_client(monkeypatch, http_handler)
    map_options = GIBSMapOptions(
        service="wmts",
        projection="epsg3857",
        layer_id="Sample_Layer",
        wmts=WMTSRequestOptions(tile_matrix="1"),
    )
    request = build_coordinates_request(map_options)
    payload = client.build_imagery_payload(request)

    assert payload.request.service == "wmts"
    assert payload.tile is not None
    assert payload.tile.tile_matrix == "1"
    assert "Sample_Layer" in payload.request.restful_url
    assert payload.debug["service"] == "wmts"


def test_wms_payload_axis_order(monkeypatch: pytest.MonkeyPatch) -> None:
    def http_handler(url: str) -> str:
        if "version=1.3.0" in url:
            return WMS_CAPABILITIES_130
        if "version=1.1.1" in url:
            return WMS_CAPABILITIES_111
        raise AssertionError(f"Unexpected WMS URL: {url}")

    client = configure_client(monkeypatch, http_handler)
    map_options = GIBSMapOptions(
        service="wms",
        projection="epsg4326",
        layer_id="Sample_Layer",
        wms=WMSRequestOptions(version="1.3.0", size_km=150.0),
    )
    request = build_coordinates_request(map_options)
    payload = client.build_imagery_payload(request)

    assert payload.request.service == "wms"
    assert payload.request.wms_version == "1.3.0"
    assert payload.bbox is not None
    assert payload.request.axis_order == "latlon"
    assert payload.request.nearest_value is True
    assert payload.debug["service"] == "wms"


def test_wmts_describe_domain_snaps_time(monkeypatch: pytest.MonkeyPatch) -> None:
    values = "".join(f"<Value>2024-01-{day:02d}</Value>" for day in range(1, 101))
    limited_capabilities = WMTS_CAPABILITIES_XML.replace(
        "<Value>2024-01-09</Value>\n        <Value>2024-01-10</Value>",
        values,
    )

    def http_handler(url: str) -> str:
        if "WMTSCapabilities.xml" in url:
            return limited_capabilities
        if "DescribeDomains" in url:
            return WMTS_DESCRIBE_DOMAIN
        raise AssertionError(f"Unexpected URL: {url}")

    client = configure_client(monkeypatch, http_handler)
    map_options = GIBSMapOptions(
        service="wmts",
        projection="epsg3857",
        layer_id="Sample_Layer",
        time_value="2024-01-11",
    )
    request = build_coordinates_request(map_options)
    payload = client.build_imagery_payload(request)

    assert payload.request.time == "2024-01-10"
    assert payload.debug["snapped"] is True


def test_imagery_download_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    def http_handler(url: str) -> str:
        if "WMTSCapabilities.xml" in url:
            return WMTS_CAPABILITIES_XML
        raise AssertionError(f"Unexpected WMTS URL: {url}")

    client = configure_client(monkeypatch, http_handler)
    map_options = GIBSMapOptions(
        service="wmts",
        projection="epsg3857",
        layer_id="Sample_Layer",
        wmts=WMTSRequestOptions(tile_matrix="1"),
    )
    request = build_coordinates_request(map_options)
    payload = client.build_imagery_payload(request)

    call_log: list[tuple[str, dict[str, str] | None]] = []

    async def fake_get(self, url: str, params: dict[str, str] | None = None):
        call_log.append((url, params))

        class Response:
            status_code = 200
            headers = {"Cache-Control": "max-age=30"}
            content = b"mock-bytes"
            text = ""

            def raise_for_status(self) -> None:
                return None

        return Response()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    first = asyncio.run(client.download_imagery(payload.request))
    second = asyncio.run(client.download_imagery(payload.request))

    assert first == second == b"mock-bytes"
    assert len(call_log) == 1
