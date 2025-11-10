from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from AEGIS.app.api.schemas.geographics import LocationSearchRequest
from AEGIS.app.utils.services.normatim import NormatimService
from AEGIS.app.utils.services.location import LocationSanitizationService

router = APIRouter(prefix="/maps", tags=["search"])

sanitization_service = LocationSanitizationService()
normatim_service = NormatimService()


###############################################################################
async def process_location_search(payload: LocationSearchRequest) -> dict[str, Any]:
    response_payload = payload.as_query_payload()

    if not payload.use_coordinates:
        sanitized_location = sanitization_service.sanitize_location_inputs(
            address=payload.address or "",
            city=payload.city,
            country=payload.country,
        )
        response_payload["sanitized_location"] = sanitized_location
        normatim_candidate = await normatim_service.extract_coordinates(
            address=sanitized_location["address"] or "",
            city=sanitized_location["city"],
            country_name=sanitized_location["country"],
            country_code=sanitized_location["country_code"],
        )
        if normatim_candidate:
            response_payload["coordinates"] = {
                "latitude": normatim_candidate.get("lat"),
                "longitude": normatim_candidate.get("lon"),
            }
            if normatim_candidate.get("bbox"):
                response_payload["bbox"] = normatim_candidate["bbox"]
            if normatim_candidate.get("confidence") is not None:
                response_payload["confidence"] = normatim_candidate["confidence"]
    else:
        if payload.latitude is not None and payload.longitude is not None:
            response_payload["coordinates"] = {
                "latitude": payload.latitude,
                "longitude": payload.longitude,
            }

    return {
        "status_message": "Map search request submitted.",
        "payload": response_payload,
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
    satellite_style: str | None = Body(default=None),
    geospatial_filter: str | None = Body(default=None),
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
            "satellite_style": satellite_style,
            "geospatial_filter": geospatial_filter,
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
