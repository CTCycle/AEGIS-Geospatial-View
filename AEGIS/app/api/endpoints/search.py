from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from AEGIS.app.api.schemas.geographics import LocationSearchRequest
from AEGIS.app.utils.services.geonames import GeonameProperties


router = APIRouter(prefix="/maps", tags=["search"])


###############################################################################
def normalize_location_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    normalized = " ".join(stripped.split())
    return normalized.lower()


###############################################################################
@router.post("/search", status_code=status.HTTP_200_OK)
async def search_by_location(payload: LocationSearchRequest) -> dict[str, Any]:
    geonames_matches: list[dict[str, Any]] = []
    if not payload.use_coordinates:
        normalized_country = normalize_location_value(payload.country)
        normalized_city = normalize_location_value(payload.city)
        normalized_address = normalize_location_value(payload.address)
        geoname_service = GeonameProperties(
            country=normalized_country,
            city=normalized_city,
            address=normalized_address,
        )
        geonames_matches = geoname_service.lookup()
    return {
        "status_message": "Map search request submitted.",
        "payload": payload.as_query_payload(),
        "geonames_candidates": geonames_matches,
    }


###############################################################################
@router.post("/agentic", status_code=status.HTTP_202_ACCEPTED)
async def search_by_agent() -> dict[str, str]:
    return {"message": "Agentic search endpoint is not implemented yet."}


