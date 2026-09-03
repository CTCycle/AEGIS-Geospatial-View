from __future__ import annotations

import asyncio

import pytest

from server.services.geospatial.openmeteo import (
    OpenMeteoRequestError,
    OpenMeteoService,
)
from server.services.geospatial.providers.base import ProviderRequest, ProviderUnavailableError
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider


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


@pytest.mark.parametrize("payload", [{}, {"elevation": []}, {"elevation": [None]}])
def test_openmeteo_service_marks_missing_or_empty_elevation_as_valid_empty(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
) -> None:
    service, _calls = _service_with_elevation_payload(monkeypatch, payload)

    result = asyncio.run(service.get_elevation(latitude=46.0, longitude=8.5))

    assert result["result_status"] == "valid_empty"
    assert result["elevation"] is None


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


def test_openmeteo_service_preserves_negative_elevation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _calls = _service_with_elevation_payload(
        monkeypatch, {"elevation": [-430.5]}
    )

    result = asyncio.run(service.get_elevation(latitude=31.5, longitude=35.5))

    assert result["result_status"] == "ok"
    assert result["elevation"] == -430.5


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
