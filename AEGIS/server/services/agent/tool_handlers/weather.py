from __future__ import annotations

from datetime import datetime, timedelta

from AEGIS.server.domain.agent.decision import ExecutionPlan, ResolvedLocation
from AEGIS.server.services.geospatial.openmeteo import OpenMeteoService


async def execute(plan: ExecutionPlan, location: ResolvedLocation) -> dict[str, object]:
    service = OpenMeteoService()
    result = await service.get_weather_forecast(latitude=location.latitude, longitude=location.longitude)
    selected = _select_requested_forecast(result, plan)
    if selected is not None:
        result["selected_forecast"] = selected
    return {
        "tool": "get_weather_forecast",
        "location": location.label,
        "result": result,
    }


def _select_requested_forecast(
    result: dict[str, object],
    plan: ExecutionPlan,
) -> dict[str, object] | None:
    if plan.temporal_mode != "forecast":
        return None
    hourly = result.get("hourly_forecast")
    if not isinstance(hourly, list):
        return None
    temporal_text = (plan.temporal_text or "").lower()
    target_date = None
    if "tomorrow" in temporal_text:
        target_date = (datetime.now() + timedelta(days=1)).date()

    fallback: dict[str, object] | None = None
    for row in hourly:
        if not isinstance(row, dict):
            continue
        raw_time = row.get("time")
        if not isinstance(raw_time, str):
            continue
        try:
            row_time = datetime.fromisoformat(raw_time)
        except ValueError:
            continue
        fallback = fallback or row
        if target_date is not None and row_time.date() == target_date and row_time.hour >= 12:
            return row
    return fallback
