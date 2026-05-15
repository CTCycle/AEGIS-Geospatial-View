from __future__ import annotations

from server.domain.agent.decision import ExecutionPlan, ResolvedLocation


async def execute(plan: ExecutionPlan, location: ResolvedLocation) -> dict[str, object]:
    _ = plan
    return {
        "tool": "location_to_coordinates",
        "location": location.label,
        "coordinates": {
            "latitude": location.latitude,
            "longitude": location.longitude,
        },
    }
