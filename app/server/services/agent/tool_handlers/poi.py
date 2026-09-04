from __future__ import annotations

from server.common.typing import json_array
from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.geospatial.overpass import OverpassService


###############################################################################
async def execute(plan: ExecutionPlan, location: ResolvedLocation) -> dict[str, object]:
    service = OverpassService()
    parameters = plan.tool_arguments
    radius_m = _positive_float(parameters.get("radius_m")) or 2500.0
    if plan.mode == "map" and "radius_m" not in parameters:
        radius_m = 3500.0
    categories = _string_list(
        parameters.get("poi_categories") or parameters.get("categories")
    )
    amenity_tags = _string_list(parameters.get("amenity_tags"))
    limit = _positive_int(parameters.get("limit"))
    result = await service.get_nearby_poi(
        latitude=location.latitude,
        longitude=location.longitude,
        radius_m=radius_m,
        amenity_tags=amenity_tags or None,
        categories=categories or None,
        limit=limit,
    )
    return {
        "tool": "get_nearby_poi",
        "location": location.label,
        "result": result,
    }


def _string_list(value: object) -> list[str]:
    return list(
        dict.fromkeys(str(item).strip() for item in json_array(value) if str(item).strip())
    )


def _positive_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value)
    return None


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None
