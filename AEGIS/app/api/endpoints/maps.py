from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from AEGIS.app.api.schemas.map_requests import MapRequest

router = APIRouter(tags=["maps"])

PLACEHOLDER_IMAGE_BASE64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAFElEQVR4nGOUm/CfARtgwio6aCUAUgQBvfoD/rAAAAAASUVORK5CYII="
)


###############################################################################
def build_caption(request: MapRequest) -> str:
    pieces: list[str] = []
    if request.filter:
        pieces.append(f"Filter: {request.filter}")
    if request.mode == "coordinates" and request.coordinates is not None:
        pieces.append(
            "Coordinates: "
            f"({request.coordinates.latitude:.4f}, {request.coordinates.longitude:.4f})"
        )
    elif request.location is not None:
        location_parts: list[str] = []
        if request.location.city:
            location_parts.append(request.location.city)
        if request.location.country:
            location_parts.append(request.location.country)
        if location_parts:
            pieces.append("Location: " + ", ".join(location_parts))
    temporal = request.temporal
    if temporal.reference_date is not None:
        pieces.append(f"Date: {temporal.reference_date.isoformat()}")
    if temporal.time_of_day is not None:
        pieces.append(f"Time: {temporal.time_of_day.strftime('%H:%M:%S')}")
    pieces.append(f"Timeline year: {temporal.timeline_year}")
    return " | ".join(pieces)


###############################################################################
@router.post("/maps", status_code=status.HTTP_200_OK)
async def render_map(request: MapRequest) -> dict[str, Any]:
    caption = build_caption(request)
    message = "Map imagery generated successfully."
    return {
        "image": {
            "data": PLACEHOLDER_IMAGE_BASE64,
            "caption": caption,
        },
        "message": message,
    }

