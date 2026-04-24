from __future__ import annotations

from AEGIS.server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from AEGIS.server.services.geospatial.openmeteo import OpenMeteoService


async def execute(plan: ExecutionPlan, location: ResolvedLocation) -> dict[str, object]:
    _ = plan
    service = OpenMeteoService()
    result = await service.get_air_quality_forecast(latitude=location.latitude, longitude=location.longitude)
    return {
        "tool": "get_air_quality_forecast",
        "location": location.label,
        "result": result,
    }
