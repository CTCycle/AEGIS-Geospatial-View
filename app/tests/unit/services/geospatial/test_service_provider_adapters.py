from __future__ import annotations
import asyncio
import pytest
from urllib.parse import parse_qs, urlparse
from server.services.geospatial.providers.base import ProviderMalformedPayloadError, ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.gbif import GBIFProvider
from server.services.geospatial.openmeteo import OpenMeteoRequestError, OpenMeteoService
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from tests.conftest import run_async_in_thread
from server.services.geospatial.overpass import OverpassService
from server.services.geospatial.providers.overpass import OverpassProvider

# --- test_gbif_provider.py ---




###############################################################################
def _provider_for_payload(
    payload: object,
) -> tuple[GBIFProvider, list[str]]:
    requested_urls: list[str] = []

    async def fetcher(url: str, _headers: dict[str, str] | None = None) -> object:
        requested_urls.append(url)
        return payload

    return GBIFProvider(fetcher=fetcher), requested_urls

###############################################################################
def test_gbif_provider_normalizes_occurrence_provenance() -> None:
    provider, requested_urls = _provider_for_payload(
        {
            "count": 2,
            "endOfRecords": True,
            "results": [
                {
                    "key": 123,
                    "scientificName": "Lynx lynx (Linnaeus, 1758)",
                    "species": "Lynx lynx",
                    "taxonKey": 2435240,
                    "decimalLatitude": 46.2,
                    "decimalLongitude": 8.8,
                    "eventDate": "2026-08-20T00:00:00",
                    "basisOfRecord": "HUMAN_OBSERVATION",
                    "datasetKey": "dataset-1",
                    "datasetTitle": "Alpine observations",
                    "coordinateUncertaintyInMeters": 50.0,
                    "issues": ["COORDINATE_ROUNDED"],
                    "license": "http://creativecommons.org/licenses/by/4.0/legalcode",
                },
                {
                    "key": 124,
                    "scientificName": "Invalid location",
                    "decimalLatitude": None,
                    "decimalLongitude": None,
                },
            ],
        }
    )
    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={
                    "limit": 100,
                    "taxonKey": 2435240,
                    "basisOfRecord": "HUMAN_OBSERVATION",
                },
            )
        )
    )

    assert response.result_status == "ok"
    assert response.result_type == "features"
    assert response.attribution == ["GBIF.org and contributing datasets"]
    assert response.payload["totalMatched"] == 2
    features = response.payload["features"]
    assert isinstance(features, list)
    assert len(features) == 1
    feature = features[0]
    assert feature["name"] == "Lynx lynx"
    assert feature["category"] == "species_occurrence"
    assert feature["url"] == "https://www.gbif.org/occurrence/123"
    assert feature["occurrenceUrl"] == "https://www.gbif.org/occurrence/123"
    assert feature["datasetUrl"] == "https://www.gbif.org/dataset/dataset-1"
    assert feature["metadata"]["basisOfRecord"] == "HUMAN_OBSERVATION"
    assert feature["metadata"]["datasetKey"] == "dataset-1"
    assert feature["metadata"]["occurrenceUrl"] == feature["occurrenceUrl"]
    assert feature["metadata"]["datasetUrl"] == feature["datasetUrl"]
    assert feature["metadata"]["coordinateUncertaintyInMeters"] == 50.0
    assert feature["metadata"]["issues"] == ["COORDINATE_ROUNDED"]
    assert feature["metadata"]["license"].startswith("http://creativecommons.org/")
    assert response.payload["provenance"] == {
        "citationRequired": True,
        "citationGuidanceUrl": "https://www.gbif.org/citation-guidelines",
        "downloadDoi": None,
    }
    assert response.warnings and "contributing datasets" in response.warnings[0]

    query = parse_qs(urlparse(requested_urls[0]).query)
    assert query["hasCoordinate"] == ["true"]
    assert query["limit"] == ["100"]
    assert query["taxonKey"] == ["2435240"]
    assert query["basisOfRecord"] == ["HUMAN_OBSERVATION"]
    assert query["geometry"][0].startswith("POLYGON((8.0 46.0")

###############################################################################
def test_gbif_provider_requires_bounded_non_antimeridian_extent() -> None:
    provider, _requested_urls = _provider_for_payload({})

    with pytest.raises(ProviderUnavailableError, match="bounded"):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=None,
                )
            )
        )

    with pytest.raises(ProviderUnavailableError, match="antimeridian"):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=(179.0, -10.0, -179.0, 10.0),
                )
            )
        )

###############################################################################
def test_gbif_provider_clamps_interactive_limit_to_300() -> None:
    provider, requested_urls = _provider_for_payload(
        {"count": 0, "endOfRecords": True, "results": []}
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={"limit": 999},
            )
        )
    )

    assert response.result_status == "valid_empty"
    assert response.payload["sampleLimit"] == 300
    assert parse_qs(urlparse(requested_urls[0]).query)["limit"] == ["300"]

###############################################################################
def test_gbif_provider_defaults_to_maximum_interactive_page() -> None:
    provider, requested_urls = _provider_for_payload(
        {"count": 0, "endOfRecords": True, "results": []}
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
            )
        )
    )

    assert response.payload["sampleLimit"] == 300
    assert parse_qs(urlparse(requested_urls[0]).query)["limit"] == ["300"]

###############################################################################
def test_gbif_provider_marks_sampled_results() -> None:
    provider, _requested_urls = _provider_for_payload(
        {
            "count": 301,
            "endOfRecords": False,
            "results": [
                {
                    "key": 1,
                    "decimalLatitude": 46.2,
                    "decimalLongitude": 8.8,
                },
                {
                    "key": 2,
                    "decimalLatitude": 46.3,
                    "decimalLongitude": 8.9,
                },
            ],
        }
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 46.0, 9.0, 47.0),
                params={"limit": 2},
            )
        )
    )

    assert response.payload["sampled"] is True
    assert response.payload["totalMatched"] == 301
    assert response.payload["sampleLimit"] == 2
    assert any("limited to 2" in warning for warning in response.warnings)

###############################################################################
def test_gbif_provider_filters_invalid_coordinates_and_supports_empty_results() -> None:
    provider, _requested_urls = _provider_for_payload(
        {
            "count": 5,
            "endOfRecords": True,
            "results": [
                {"key": 1, "decimalLatitude": 46.0, "decimalLongitude": 8.0},
                {"key": 2, "decimalLatitude": 91.0, "decimalLongitude": 8.0},
                {"key": 3, "decimalLatitude": 46.0, "decimalLongitude": 181.0},
                {"key": 4, "decimalLatitude": "not-a-number", "decimalLongitude": 8.0},
                {"key": 5, "decimalLatitude": float("nan"), "decimalLongitude": 8.0},
            ],
        }
    )

    response = asyncio.run(
        provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 45.0, 9.0, 47.0),
            )
        )
    )

    assert response.result_status == "ok"
    assert [feature["id"] for feature in response.payload["features"]] == ["1"]

    empty_provider, _requested_urls = _provider_for_payload(
        {"count": 0, "endOfRecords": True, "results": []}
    )
    empty_response = asyncio.run(
        empty_provider.fetch(
            ProviderRequest(
                capability_id="gbif_species_occurrences",
                bbox=(8.0, 45.0, 9.0, 47.0),
            )
        )
    )
    assert empty_response.result_status == "valid_empty"
    assert empty_response.payload["features"] == []

###############################################################################
@pytest.mark.parametrize("payload", [[], {}, {"results": {}}])
def test_gbif_provider_rejects_malformed_payloads(payload: object) -> None:
    provider, _requested_urls = _provider_for_payload(payload)

    with pytest.raises(ProviderMalformedPayloadError):
        asyncio.run(
            provider.fetch(
                ProviderRequest(
                    capability_id="gbif_species_occurrences",
                    bbox=(8.0, 45.0, 9.0, 47.0),
                )
            )
        )

# --- test_openmeteo_elevation.py ---




###############################################################################
class StubOpenMeteoService(OpenMeteoService):

    # -------------------------------------------------------------------------
    def __init__(self) -> None:
        self.elevation_base_url = "https://api.open-meteo.com/v1/elevation"
        self.weather_base_url = "https://api.open-meteo.com/v1/forecast"
        self.air_quality_base_url = (
            "https://air-quality-api.open-meteo.com/v1/air-quality"
        )

    # -------------------------------------------------------------------------
    async def get_elevation(
        self, *, latitude: float, longitude: float
    ) -> dict[str, object]:
        return {
            "provider": "openmeteo",
            "kind": "terrain_elevation",
            "source_url": self.elevation_base_url,
            "fetched_at": "2026-09-03T12:00:00+00:00",
            "result_status": "ok",
            "result_type": "metadata",
            "partial": False,
            "latitude": latitude,
            "longitude": longitude,
            "elevation": 1234.0,
            "resolved_at": "2026-09-03T12:00:00+00:00",
            "observation_time": None,
            "units": {"elevation": "m"},
            "requested_variables": ["elevation"],
            "request_parameters": {
                "latitude": f"{latitude:.6f}",
                "longitude": f"{longitude:.6f}",
            },
            "spatial_resolution": "90 m Copernicus DEM GLO-90",
            "coverage": {
                "type": "point",
                "latitude": latitude,
                "longitude": longitude,
            },
            "attribution": "Data from Open-Meteo; Copernicus DEM GLO-90",
        }

###############################################################################
def test_openmeteo_provider_routes_and_normalizes_elevation() -> None:
    provider = OpenMeteoProvider(service=StubOpenMeteoService())
    request = ProviderRequest(
        capability_id="openmeteo_elevation",
        bbox=(8.5, 46.0, 8.5, 46.0),
    )

    response = asyncio.run(provider.fetch(request))

    assert response.result_status == "ok"
    assert response.result_type == "features"
    assert response.spatial_resolution == "90 m Copernicus DEM GLO-90"
    assert response.units == {"elevation": "m"}
    assert response.source_url == "https://api.open-meteo.com/v1/elevation"
    assert response.payload["kind"] == "terrain_elevation"
    features = response.payload["features"]
    assert isinstance(features, list)
    assert len(features) == 1
    feature = features[0]
    assert feature["category"] == "terrain"
    assert feature["elevation"] == 1234.0
    assert feature["latitude"] == 46.0
    assert feature["longitude"] == 8.5

###############################################################################
def _service_with_elevation_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> tuple[OpenMeteoService, list[dict[str, object]]]:
    service = OpenMeteoService(
        elevation_base_url="https://example.test/elevation",
        min_call_interval_s=0.05,
    )
    calls: list[dict[str, object]] = []

    def fake_get_json(
        *, endpoint: str, params: dict[str, str], provider_key: str
    ) -> dict[str, object]:
        calls.append(
            {"endpoint": endpoint, "params": params, "provider_key": provider_key}
        )
        return payload

    monkeypatch.setattr(service, "_get_json", fake_get_json)
    return service, calls

###############################################################################
def test_openmeteo_service_parses_numeric_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, calls = _service_with_elevation_payload(
        monkeypatch, {"elevation": [1234.5]}
    )

    result = asyncio.run(service.get_elevation(latitude=46.0, longitude=8.5))

    assert result["result_status"] == "ok"
    assert result["elevation"] == 1234.5
    assert calls == [
        {
            "endpoint": "https://example.test/elevation",
            "params": {"latitude": "46.000000", "longitude": "8.500000"},
            "provider_key": "openmeteo_elevation",
        }
    ]

###############################################################################
@pytest.mark.parametrize("payload", [{}, {"elevation": []}, {"elevation": [None]}])
def test_openmeteo_service_marks_missing_or_empty_elevation_as_valid_empty(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    service, _calls = _service_with_elevation_payload(monkeypatch, payload)

    result = asyncio.run(service.get_elevation(latitude=46.0, longitude=8.5))

    assert result["result_status"] == "valid_empty"
    assert result["elevation"] is None

###############################################################################
@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"elevation": "1234"}, "must be an array"),
        ({"elevation": ["1234"]}, "finite numeric value"),
    ],
)
def test_openmeteo_service_rejects_malformed_elevation_payload(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    message: str,
) -> None:
    service, _calls = _service_with_elevation_payload(monkeypatch, payload)

    with pytest.raises(OpenMeteoRequestError, match=message):
        asyncio.run(service.get_elevation(latitude=46.0, longitude=8.5))

###############################################################################
def test_openmeteo_service_preserves_negative_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _calls = _service_with_elevation_payload(
        monkeypatch, {"elevation": [-430.5]}
    )

    result = asyncio.run(service.get_elevation(latitude=31.5, longitude=35.5))

    assert result["result_status"] == "ok"
    assert result["elevation"] == -430.5

###############################################################################
def test_openmeteo_service_propagates_provider_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OpenMeteoService(
        elevation_base_url="https://example.test/elevation",
        min_call_interval_s=0.05,
    )

    def fail_get_json(**_kwargs: object) -> dict[str, object]:
        raise OpenMeteoRequestError("HTTP 503 from Open-Meteo")

    monkeypatch.setattr(service, "_get_json", fail_get_json)

    with pytest.raises(OpenMeteoRequestError, match="HTTP 503"):
        asyncio.run(service.get_elevation(latitude=46.0, longitude=8.5))

###############################################################################
def test_openmeteo_provider_translates_service_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = OpenMeteoService(
        elevation_base_url="https://example.test/elevation",
        min_call_interval_s=0.05,
    )

    async def fail_get_elevation(**_kwargs: float) -> dict[str, object]:
        raise OpenMeteoRequestError("HTTP 503 from Open-Meteo")

    monkeypatch.setattr(service, "get_elevation", fail_get_elevation)

    with pytest.raises(ProviderUnavailableError, match="HTTP 503"):
        asyncio.run(
            OpenMeteoProvider(service=service).fetch(
                ProviderRequest(
                    capability_id="openmeteo_elevation",
                    bbox=(8.5, 46.0, 8.5, 46.0),
                )
            )
        )

# --- test_overpass_residential_buildings.py ---



###############################################################################
class _BuildingService:
    default_radius_m = 1500.0

    # -------------------------------------------------------------------------
    async def get_residential_buildings(self, **kwargs):
        assert kwargs["latitude"] == 41.89
        assert kwargs["longitude"] == 12.49
        return {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[12.49, 41.89], [12.50, 41.89], [12.49, 41.89]]
                        ],
                    },
                    "properties": {"building": "apartments"},
                }
            ],
        }

###############################################################################
def test_overpass_provider_routes_residential_capability_separately() -> None:
    async def _run() -> None:
        response = await OverpassProvider(service=_BuildingService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="overpass_residential_buildings",
                params={"latitude": 41.89, "longitude": 12.49},
            )
        )
        assert response.payload["type"] == "FeatureCollection"
        assert response.payload["features"][0]["properties"]["building"] == "apartments"
        assert "OpenStreetMap" in response.attribution[0]

    run_async_in_thread(_run())

###############################################################################
def test_residential_building_normalization_rejects_non_polygons() -> None:
    service = OverpassService()
    service._query_buildings = lambda **kwargs: {  # type: ignore[method-assign]
        "elements": [
            {"type": "node", "id": 1, "tags": {"building": "house"}},
            {
                "type": "way",
                "id": 2,
                "tags": {"building": "commercial"},
                "geometry": [
                    {"lat": 41.0, "lon": 12.0},
                    {"lat": 41.1, "lon": 12.1},
                    {"lat": 41.0, "lon": 12.0},
                ],
            },
        ]
    }
    payload = run_async_in_thread(
        service.get_residential_buildings(
            latitude=41.89,
            longitude=12.49,
            limit=10,
        )
    )
    assert payload["features"] == []