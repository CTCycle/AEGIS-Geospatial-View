from __future__ import annotations

from typing import Any
import math

from shapely.geometry import Point

from server.services.geospatial.land_mask import LandMask
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


def grid_points(
    bbox: tuple[float, float, float, float],
    max_points: int = 100,
    mask: LandMask | None = None,
) -> tuple[list[tuple[float, float]], float, int]:
    """Return (latitude, longitude) cell centres, angular spacing, and the
    number of candidate centres excluded by the mask.

    With a mask the regular grid is densified until the masked centres
    approach the budget, so sea or out-of-region cells do not consume it.
    """
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and -85 <= south < north <= 85):
        raise ValueError("Grid bbox must be ordered and within longitude / latitude bounds.")
    budget = max(1, min(1000, max_points))
    points, spacing = _regular_grid(bbox, budget)
    if mask is None:
        return points, spacing, 0
    def sample(cells: int) -> tuple[list[tuple[float, float]], float, int]:
        candidates, cell_spacing = _regular_grid(bbox, cells)
        kept = [point for point in candidates if mask.contains(Point(point[1], point[0]))]
        return kept, cell_spacing, len(candidates) - len(kept)

    low, best = budget, sample(budget)
    high: int | None = None
    for _ in range(10):
        if len(best[0]) >= 0.85 * budget or low >= budget * 64:
            break
        if high is None:
            cells = min(budget * 64, int(low * min(4.0, 0.95 * budget / max(len(best[0]), 1))) + 1)
        else:
            cells = (low + high) // 2
            if cells <= low:
                break
        result = sample(cells)
        if len(result[0]) > budget:
            high = cells
        else:
            low, best = cells, result
    return best


def _regular_grid(bbox: tuple[float, float, float, float], cells: int) -> tuple[list[tuple[float, float]], float]:
    west, south, east, north = bbox
    width, height = east - west, north - south
    columns = max(1, min(cells, round(math.sqrt(cells * width / height))))
    rows = max(1, cells // columns)
    dx, dy = width / columns, height / rows
    return ([(round(south + (row + 0.5) * dy, 5), round(west + (col + 0.5) * dx, 5))
             for row in range(rows) for col in range(columns)], max(dx, dy))
