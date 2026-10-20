from __future__ import annotations

from typing import Any
import math

from server.services.geospatial.providers.base import ProviderRequest

###############################################################################
def request_center(request: ProviderRequest) -> tuple[float, float]:
    latitude = _number_param(request.params, "latitude", "lat")
    longitude = _number_param(request.params, "longitude", "lon", "lng")
    if latitude is not None and longitude is not None:
        return latitude, longitude
    if request.bbox is not None:
        min_lon, min_lat, max_lon, max_lat = request.bbox
        return (min_lat + max_lat) / 2.0, (min_lon + max_lon) / 2.0
    raise ValueError("Provider request requires latitude/longitude or bbox.")

###############################################################################
def request_radius_m(request: ProviderRequest, default_radius_m: float) -> float:
    value = _number_param(request.params, "radius_m", "radius")
    if value is not None and value > 0:
        return value
    return default_radius_m

###############################################################################
def _number_param(params: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = params.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def grid_points(bbox: tuple[float, float, float, float], max_points: int = 100) -> tuple[list[tuple[float, float]], float]:
    """Return (latitude, longitude) cell centres and maximum angular spacing."""
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError("Grid bbox must be ordered and within longitude / latitude bounds.")
    cap = max(1, min(100, max_points))
    width, height = east - west, north - south
    columns = max(1, min(cap, round(math.sqrt(cap * width / height))))
    rows = max(1, cap // columns)
    dx, dy = width / columns, height / rows
    return ([(round(south + (row + 0.5) * dy, 5), round(west + (col + 0.5) * dx, 5))
             for row in range(rows) for col in range(columns)], max(dx, dy))
