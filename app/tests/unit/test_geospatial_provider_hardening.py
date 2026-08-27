from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from tests.conftest import run_async_in_thread

from server.services.geospatial.openaq import (
    OpenAQRequestError,
    OpenAQService,
)
from server.services.geospatial.providers import http as provider_http
from server.services.geospatial.providers.base import (
    ProviderAuthError,
    ProviderInvalidQueryError,
    ProviderMalformedPayloadError,
    ProviderRateLimitError,
    ProviderRequest,
    ProviderUnavailableError,
)
from server.domain.llm.types import LLMToolDefinition
from server.services.agent.tool_registry import ToolRegistry
from server.services.geospatial.providers.census import CensusProvider
from server.services.geospatial.providers.local_open_data import LocalOpenDataProvider
from server.services.geospatial.providers.noaa import NOAAProvider

###############################################################################
def test_shared_http_rejects_redirects_and_limits_response_bytes(monkeypatch) -> None:
    class _Response:
        status_code = 200
        headers = {"content-length": "4"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_bytes(self):
            yield b"1234"

    class _Client:
        def stream(self, *args, **kwargs):
            return _Response()

    monkeypatch.setattr(provider_http, "_ASYNC_HTTP_CLIENT", _Client())
    with pytest.raises(ProviderUnavailableError, match="size limit"):
        run_async_in_thread(provider_http.fetch_bytes_url("https://example.test/data", max_bytes=3))

    with pytest.raises(ProviderUnavailableError, match="redirect"):
        provider_http._raise_for_status(httpx.Response(302, headers={"location": "/next"}))

###############################################################################
def test_shared_http_preserves_retry_after_without_exposing_headers() -> None:
    with pytest.raises(ProviderRateLimitError) as error:
        provider_http._raise_for_status(httpx.Response(429, headers={"retry-after": "7"}))

    assert error.value.retry_after_seconds == 7.0
    assert "retry-after" not in str(error.value).lower()

###############################################################################
def test_openaq_v3_joins_location_sensors_to_latest_measurements() -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    def requester(url: str, headers: dict[str, str]):
        calls.append((url, headers))
        if "/locations/42/latest" in url:
            return {
                "results": [
                    {
                        "locationsId": 42,
                        "sensorsId": 9001,
                        "value": 8.5,
                        "datetime": {"utc": "2026-08-27T10:00:00Z"},
                        "coordinates": {"latitude": 41.9, "longitude": 12.5},
                    }
                ]
            }
        return {
            "results": [
                {
                    "id": 42,
                    "name": "Roma station",
                    "coordinates": {"latitude": 41.9, "longitude": 12.5},
                    "instruments": [
                        {
                            "sensors": [
                                {
                                    "id": 9001,
                                    "parameter": {"name": "pm2.5", "units": "µg/m³"},
                                }
                            ]
                        }
                    ],
                }
            ]
        }

    response = run_async_in_thread(
        OpenAQService(api_key="secret", requester=requester).get_nearby_measurements(
            41.9, 12.5, 5000
        )
    )

    assert response["locations"][0]["measurements"]["pm25"]["value"] == 8.5
    assert len(calls) == 2
    assert "order_by=id" in calls[0][0]
    assert "radius=5000" in calls[0][0]
    assert all("secret" not in url for url, _ in calls)
    assert all(headers["X-API-Key"] == "secret" for _, headers in calls)

###############################################################################
def test_openaq_request_failure_is_not_converted_to_empty_data() -> None:
    def requester(url: str, headers: dict[str, str]):
        raise OpenAQRequestError("OpenAQ request failed.")

    with pytest.raises(OpenAQRequestError):
        run_async_in_thread(
            OpenAQService(api_key="secret", requester=requester).get_nearby_measurements(
                41.9, 12.5
            )
        )

###############################################################################
def test_noaa_coops_discovers_stations_and_requests_station_observations() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        calls.append(url)
        if "stations.json" in url:
            return {
                "stations": [
                    {"id": "9414290", "name": "San Francisco", "lat": 37.8, "lng": -122.5}
                ]
            }
        query = parse_qs(urlsplit(url).query)
        assert query["station"] == ["9414290"]
        assert query["product"] == ["water_level"]
        assert query["datum"] == ["MLLW"]
        return {"data": [{"t": "2026-08-27 10:00", "v": "1.25"}]}

    response = run_async_in_thread(
        NOAAProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="noaa_coops_water_levels",
                bbox=(-123.0, 37.0, -122.0, 38.0),
                params={"live": True},
            )
        )
    )

    assert len(calls) == 2
    assert response.payload["features"][0]["id"] == "9414290"
    assert response.payload["features"][0]["value"] == 1.25

###############################################################################
def test_census_demographics_discovers_boundary_layer_and_joins_acs() -> None:
    calls: list[str] = []

    async def fetcher(url: str, headers=None):  # noqa: ANN001
        calls.append(url)
        if url.endswith("Tracts_Blocks/MapServer?f=json"):
            return {
                "layers": [
                    {"id": 3, "name": "ACS 2024", "subLayerIds": [4]},
                ]
            }
        if url.endswith("Tracts_Blocks/MapServer/3?f=json"):
            return {"layers": [{"id": 4, "name": "Census Tracts"}]}
        if "/MapServer/4/query" in url:
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "tract-1",
                        "properties": {"GEOID": "06001400100"},
                        "geometry": {"type": "Polygon", "coordinates": []},
                    }
                ],
            }
        if "api.census.gov/data/2024/acs/acs5" in url:
            return [
                ["NAME", "B01003_001E", "state", "county", "tract"],
                ["Test tract", "1234", "06", "001", "400100"],
            ]
        raise AssertionError(f"Unexpected Census URL: {url}")

    response = run_async_in_thread(
        CensusProvider(fetcher=fetcher).fetch(
            ProviderRequest(
                capability_id="census_tigerweb_demographics",
                bbox=(-123.0, 37.0, -122.0, 38.0),
                params={"live": True, "vintage": "2024"},
            )
        )
    )

    feature = response.payload["features"][0]
    assert response.payload["boundaryLayerId"] == "4"
    assert response.payload["joinCount"] == 1
    assert feature["properties"]["population"] == 1234
    assert any("api.census.gov/data/2024" in url for url in calls)

###############################################################################
def test_local_open_data_requires_configured_source_id_and_preserves_geojson_mode() -> None:
    async def fetcher(url: str, headers=None):  # noqa: ANN001
        return {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}, "geometry": None}],
        }

    provider = LocalOpenDataProvider(
        source_map={"local_parcels": "https://agency.example/parcels.json"},
        fetcher=fetcher,
    )
    with pytest.raises(ProviderInvalidQueryError):
        run_async_in_thread(
            provider.fetch(
                ProviderRequest(
                    capability_id="local_parcels",
                    params={"source_url": "https://attacker.example/metadata.json"},
                )
            )
        )

    response = run_async_in_thread(
        provider.fetch(ProviderRequest(capability_id="local_parcels"))
    )
    assert response.payload["renderingMode"] == "geojson"
    assert response.payload["sourceId"] == "local_parcels"

###############################################################################
@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (ProviderAuthError("missing"), "auth_required"),
        (ProviderRateLimitError("limited"), "rate_limited"),
        (ProviderInvalidQueryError("invalid"), "invalid_query"),
        (ProviderMalformedPayloadError("malformed"), "malformed_response"),
        (ProviderUnavailableError("unavailable"), "provider_unavailable"),
    ],
)
def test_native_tool_maps_provider_failures_to_canonical_codes(
    provider_error: Exception, expected_code: str
) -> None:
    registry = ToolRegistry(runtime_registry=object())  # type: ignore[arg-type]

    async def handler(arguments, context):  # noqa: ANN001
        del arguments, context
        raise provider_error

    registry.register_native_tool(
        LLMToolDefinition(
            name="provider_tool",
            description="Provider tool",
            parameters_json_schema={
                "type": "object",
                "additionalProperties": False,
            },
        ),
        handler,
    )

    envelope = run_async_in_thread(
        registry.execute_native_tool("provider_tool", {}, None)
    )

    assert envelope.ok is False
    assert envelope.error is not None
    assert envelope.error.code == expected_code
