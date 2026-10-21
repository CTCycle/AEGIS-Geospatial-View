from __future__ import annotations

from tests.conftest import run_async_in_thread

from server.services.geospatial.providers.base import ProviderRequest
from server.services.geospatial.providers.openmeteo import OpenMeteoProvider
from server.services.geospatial.providers._request import grid_points
from server.services.geospatial.openmeteo import OpenMeteoService
from server.services.geospatial.land_mask import country_shapes, land_mask
from server.services.catalog.loader import find_macro_region_entry, load_macro_regions
from shapely.geometry import Point
from urllib.parse import urlencode
from unittest.mock import patch
import pytest

###############################################################################
class _OpenMeteoService:

    # -------------------------------------------------------------------------
    async def get_weather_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "weather_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "current": {
                "wind_speed_10m": 7,
                "wind_direction_10m": 270,
                "surface_pressure": 1008,
                "relative_humidity_2m": 55,
            },
            "hourly_preview": [],
            "attribution": "Data from Open-Meteo",
        }

    # -------------------------------------------------------------------------
    async def get_air_quality_forecast(self, *, latitude: float, longitude: float):
        return {
            "kind": "air_quality_forecast",
            "latitude": latitude,
            "longitude": longitude,
            "hourly_preview": [{"pm2_5": 8, "pm10": 12}],
            "attribution": "Data from Open-Meteo",
        }

###############################################################################
def test_openmeteo_wind_sampling_emits_arrow_metadata() -> None:
    response = run_async_in_thread(
        OpenMeteoProvider(service=_OpenMeteoService()).fetch(  # type: ignore[arg-type]
            ProviderRequest(
                capability_id="openmeteo_pressure_humidity_wind",
                params={"latitude": 41.9, "longitude": 12.5},
            )
        )
    )

    feature = response.payload["features"][0]
    assert response.payload["renderingMode"] == "clustered-points"
    assert feature["metadata"]["windArrow"] == {"speed": 7, "direction": 270}


###############################################################################
@pytest.mark.parametrize("bbox", [(-180, -85, 180, 85), (-25, 34, 45, 72), (8, 45, 8.1, 70)])
def test_weather_grid_cap_and_interior_centres(bbox):
    points, spacing, excluded = grid_points(bbox)
    assert 1 <= len(points) <= 100 and spacing > 0 and excluded == 0
    assert all(bbox[0] < lon < bbox[2] and bbox[1] < lat < bbox[3] for lat, lon in points)


###############################################################################
def test_region_mask_excludes_sea_and_non_member_land():
    europe = find_macro_region_entry("Europe")
    assert europe is not None
    mask = land_mask(europe.bbox, europe.countries)
    inside = {name: mask.contains(Point(lon, lat)) for name, (lon, lat) in {
        "Lisbon": (-9.14, 38.72), "Warsaw": (21.01, 52.23), "Rabat": (-6.84, 34.02),
        "Ankara": (32.85, 39.93), "Tunis": (10.18, 36.8), "Bay of Biscay": (-5.0, 45.5)}.items()}
    assert inside == {"Lisbon": True, "Warsaw": True, "Rabat": False, "Ankara": False, "Tunis": False, "Bay of Biscay": False}
    points, spacing, excluded = grid_points(europe.bbox, 300, mask)
    assert 255 <= len(points) <= 300 and excluded > 0 and spacing < 3
    assert all(mask.contains(Point(lon, lat)) for lat, lon in points)


###############################################################################
def test_macro_region_members_have_shapes():
    shapes = country_shapes()
    assert all(code in shapes for region in load_macro_regions() for code in region.countries)


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_region_refinement_future_hours_and_provenance():
    requested: list[list[tuple[float, float]]] = []

    ###############################################################################
    class Service:
        weather_base_url = "https://api.open-meteo.com/v1/forecast"

        # -------------------------------------------------------------------------
        async def get_weather_grid(self, points, past_days):
            requested.append(points)
            row = {"elevation": 0, "current": {"time": "2026-10-20T12:00", "temperature_2m": 30},
                   "hourly": {"time": ["2026-10-20T11:00", "2026-10-20T12:00", "2026-10-20T13:00"],
                              "temperature_2m": [28, 30, 99], "precipitation": [2, 3, 100]}}
            return [{**row, "current": {}}] + [row for _ in points[1:]]
    europe = find_macro_region_entry("Europe")
    assert europe is not None
    result = await OpenMeteoProvider(service=Service()).fetch(ProviderRequest(
        capability_id="openmeteo_weather_forecast", bbox=europe.bbox,
        params={"sampling": "area", "macro_region": "Europe"}))
    features = result.payload["features"]
    mask = land_mask(europe.bbox, europe.countries)
    # Elevation zero is no longer treated as sea; the region mask decides.
    assert all(mask.contains(Point(lon, lat)) for batch in requested for lat, lon in batch)
    assert features[0]["precipitation_sum_mm"] == 5 and features[0]["temperature_2m_max_c"] == 30
    assert len(requested) == 2 and 0 < len(requested[1]) <= 80
    assert {f["sample_stage"] for f in features} == {"coarse", "refined"}
    assert result.coverage["region"] == "Europe" and result.coverage["excluded_outside_region_points"] > 0
    assert result.coverage["refined_point_count"] == len(requested[1]) - 1
    assert result.coverage["value_kind"] == "model_estimate"
    assert result.result_status == "partial"
    assert result.units["precipitation_sum_mm"] == "mm"


###############################################################################
@pytest.mark.asyncio
async def test_weather_grid_batches_requests_under_8kb():
    service = OpenMeteoService()
    calls = []
    def get_json(**kwargs):
        calls.append(kwargs)
        return {"locations": [{"elevation": 10}] * len(kwargs["params"]["latitude"].split(","))}
    with patch.object(service, "_get_json", side_effect=get_json):
        points, _, _ = grid_points((-180, -85, 180, 85), 300, land_mask((-180, -85, 180, 85)))
        result = await service.get_weather_grid(points, 30)
    assert len(result) == len(points) and len(calls) == 3
    assert all(call["params"]["past_days"] == "14" for call in calls)
    assert all(len(call["endpoint"] + "?" + urlencode(call["params"])) < 8192 for call in calls)
