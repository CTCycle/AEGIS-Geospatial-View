from __future__ import annotations

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from server.services.geospatial.overpass import OverpassService


###############################################################################
async def execute(plan: ExecutionPlan, location: ResolvedLocation) -> dict[str, object]:
    service = OverpassService()
    radius_m = 2500.0
    if plan.mode == "map":
        radius_m = 3500.0
    result = await service.get_nearby_poi(latitude=location.latitude, longitude=location.longitude, radius_m=radius_m)
    return {
        "tool": "get_nearby_poi",
        "location": location.label,
        "result": result,
    }
