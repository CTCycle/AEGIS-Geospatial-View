from __future__ import annotations

import asyncio
from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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
async def process_location_search(payload: LocationSearchRequest) -> dict[str, Any]:
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
        geonames_matches = await asyncio.to_thread(geoname_service.lookup)
    return {
        "status_message": "Map search request submitted.",
        "payload": payload.as_query_payload(),
        "geonames_candidates": geonames_matches,
    }


###############################################################################
@router.post("/search", status_code=status.HTTP_200_OK)
async def search_by_location(
    datetime_value: datetime | str | None = Body(default=None, alias="datetime"),
    reference_date: date | str | None = Body(default=None),
    time_of_day: time | str | None = Body(default=None),
    timeline_year: int | None = Body(default=None),
    country: str | None = Body(default=None),
    city: str | None = Body(default=None),
    address: str | None = Body(default=None),
    use_coordinates: bool = Body(default=False),
    latitude: float | None = Body(default=None),
    longitude: float | None = Body(default=None),
    filter_value: str | None = Body(default=None, alias="filter"),
) -> JSONResponse:
    try:
        payload_data: dict[str, Any] = {
            "datetime": datetime_value,
            "reference_date": reference_date,
            "time_of_day": time_of_day,
            "timeline_year": timeline_year,
            "country": country,
            "city": city,
            "address": address,
            "use_coordinates": use_coordinates,
            "latitude": latitude,
            "longitude": longitude,
            "filter": filter_value,
        }
        payload = LocationSearchRequest.model_validate(payload_data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    response_payload = await process_location_search(payload)
    serialized_payload = jsonable_encoder(response_payload)
    return JSONResponse(content=serialized_payload)


###############################################################################
@router.post("/agentic", status_code=status.HTTP_202_ACCEPTED)
async def search_by_agent() -> dict[str, str]:
    return {"message": "Agentic search endpoint is not implemented yet."}
