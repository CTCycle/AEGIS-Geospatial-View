from __future__ import annotations

import asyncio
import base64
from collections.abc import Callable
from datetime import date, datetime, time
from typing import Any

from fastapi import APIRouter, Body, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from AEGIS.src.app.backend.schemas.geographics import LocationSearchRequest
from AEGIS.src.packages.utils.services.geospatial.gibs import (
    GIBSRequestError,
    GIBSService,
    GIBSValidationError,
)
from AEGIS.src.packages.utils.services.geospatial.normatim import NormatimService
from AEGIS.src.packages.utils.services.sanitization import LocationSanitizationService

router = APIRouter(prefix="/maps", tags=["search"])

sanitization_service = LocationSanitizationService()
normatim_service = NormatimService()
gibs_service = GIBSService()

type CoordinatePair = tuple[float, float]
type EncodingStrategy = Callable[[bytes], str]
DEFAULT_GIBS_LAYER = "VIIRS_SNPP_CorrectedReflectance_TrueColor"

###############################################################################
async def get_location_coordinates(payload: LocationSearchRequest) -> dict[str, object]:
    response_payload = payload.model_dump()
    if not payload.use_coordinates:
        sanitized_location = await asyncio.to_thread(
            sanitization_service.sanitize_location_inputs,
            payload.address or "",
            payload.city,
            payload.country,
        )
        response_payload["sanitized_location"] = sanitized_location
        normatim_candidate = await normatim_service.extract_coordinates(
            address=sanitized_location["address"] or "",
            city=sanitized_location["city"],
            country_name=sanitized_location["country"],
            country_code=sanitized_location["country_code"],
        )
        if normatim_candidate:
            latitude = normatim_candidate.get("lat")
            longitude = normatim_candidate.get("lon")
            if latitude is not None and longitude is not None:
                try:
                    lat_value = float(latitude)
                    lon_value = float(longitude)
                except (TypeError, ValueError):
                    lat_value = None
                    lon_value = None
                if lat_value is not None and lon_value is not None:
                    response_payload["latitude"] = lat_value
                    response_payload["longitude"] = lon_value
                    
            if normatim_candidate.get("bbox"):
                response_payload["bbox"] = normatim_candidate["bbox"]
            if normatim_candidate.get("confidence") is not None:
                response_payload["confidence"] = normatim_candidate["confidence"]
    else:
        if payload.latitude is not None and payload.longitude is not None:
            response_payload["latitude"] = payload.latitude
            response_payload["longitude"] = payload.longitude
            bbox = await normatim_service.extract_bbox_from_coordinates(
                latitude=payload.latitude,
                longitude=payload.longitude,
            )
            if bbox:
                response_payload["bbox"] = bbox

    return response_payload


###############################################################################
def resolve_imagery_date(payload: LocationSearchRequest) -> str:
    if payload.reference_date:
        return payload.reference_date.isoformat()
    if payload.datetime:
        return payload.datetime.date().isoformat()
    raise GIBSValidationError(
        "Provide reference_date or datetime to determine imagery date."
    )


###############################################################################
def resolve_imagery_layer(payload: LocationSearchRequest) -> str:
    layer_candidates = (
        payload.filter,
        payload.geospatial_filter,
    )
    for candidate in layer_candidates:
        if candidate is None:
            continue
        normalized = str(candidate).strip()
        if not normalized or normalized.lower() == "none":
            continue
        return normalized
    return DEFAULT_GIBS_LAYER


###############################################################################
def extract_coordinate_pair(
    payload: LocationSearchRequest, response_payload: dict[str, Any]
) -> CoordinatePair | None:
    lat_value = payload.latitude
    lon_value = payload.longitude
    if lat_value is not None and lon_value is not None:
        return lon_value, lat_value
    coordinates = response_payload.get("coordinates")
    if isinstance(coordinates, dict):
        lat_candidate = coordinates.get("latitude")
        lon_candidate = coordinates.get("longitude")
        if isinstance(lat_candidate, (int, float)) and isinstance(
            lon_candidate, (int, float)
        ):
            return float(lon_candidate), float(lat_candidate)
    lat_literal = response_payload.get("latitude")
    lon_literal = response_payload.get("longitude")
    if isinstance(lat_literal, (int, float)) and isinstance(lon_literal, (int, float)):
        return float(lon_literal), float(lat_literal)
    return None


###############################################################################
def parse_bbox_values(candidate: Any) -> list[float] | None:
    if isinstance(candidate, (list, tuple)) and len(candidate) == 4:
        parsed: list[float] = []
        try:
            for value in candidate:
                parsed.append(float(value))
        except (TypeError, ValueError):
            return None
        return parsed
    return None


###############################################################################
def resolve_bbox_candidate(
    payload: LocationSearchRequest, response_payload: dict[str, Any]
) -> tuple[list[float] | None, str | None]:
    if payload.bbox:
        normalized = parse_bbox_values(payload.bbox)
        if normalized:
            return normalized, payload.image_crs
    inherited = parse_bbox_values(response_payload.get("bbox"))
    if inherited:
        return inherited, "EPSG:4326"
    return None, None


###############################################################################
def harmonize_bbox_crs(
    bbox: list[float] | None, *, source_crs: str | None, target_crs: str
) -> list[float] | None:
    if bbox is None:
        return None
    target = (target_crs or "").upper()
    if not target:
        raise GIBSValidationError("Satellite imagery CRS is required.")
    source = (source_crs or target).upper()
    if source == target:
        return bbox
    supported = {"EPSG:4326", "EPSG:3857"}
    if source not in supported or target not in supported:
        raise GIBSValidationError(
            f"Unsupported bbox reprojection from {source} to {target}."
        )
    return gibs_service.reproject_bbox(bbox, target)


###############################################################################
async def fetch_satellite_imagery(
    payload: LocationSearchRequest, response_payload: dict[str, Any]
) -> dict[str, Any]:
    coordinate_pair = extract_coordinate_pair(payload, response_payload)
    bbox_candidate, bbox_source_crs = resolve_bbox_candidate(payload, response_payload)
    bbox = harmonize_bbox_crs(
        bbox_candidate, source_crs=bbox_source_crs, target_crs=payload.image_crs
    )
    if not bbox and not coordinate_pair:
        raise GIBSValidationError(
            "Provide coordinates or bbox for satellite imagery requests."
        )
    lon = coordinate_pair[0] if coordinate_pair else None
    lat = coordinate_pair[1] if coordinate_pair else None
    imagery_date = resolve_imagery_date(payload)
    layer = resolve_imagery_layer(payload)
    gibs_arguments = {
        "lon": lon,
        "lat": lat,
        "bbox": bbox,
        "radius_m": payload.radius_m,
        "date": imagery_date,
        "layer": layer,
        "width": payload.image_width,
        "height": payload.image_height,
        "crs": payload.image_crs,
        "format": payload.image_format,
    }
    gibs_response = await asyncio.to_thread(gibs_service.fetch_image, **gibs_arguments)
    image_bytes = gibs_response.pop("image_bytes", b"")
    encoder: EncodingStrategy = lambda data: base64.b64encode(data).decode("ascii")
    encoded_image = encoder(image_bytes)
    gibs_response["image_base64"] = encoded_image
    gibs_response["mime"] = gibs_response.get("mime", payload.image_format)
    return gibs_response


###############################################################################
async def process_location_search(payload: LocationSearchRequest) -> dict[str, Any]:
    search_payload = await get_location_coordinates(payload)
    try:
        satellite_payload = await fetch_satellite_imagery(payload, search_payload)
    except GIBSValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except GIBSRequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    search_payload["satellite_imagery"] = satellite_payload

    return {
        "status_message": "Map search request submitted.",
        "payload": search_payload,
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
    geospatial_filter: str | None = Body(default=None),
    bbox: list[float] | None = Body(default=None),
    radius_m: float | None = Body(default=None),
    image_width: int | None = Body(default=None),
    image_height: int | None = Body(default=None),
    image_crs: str | None = Body(default=None),
    image_format: str | None = Body(default=None),
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
            "geospatial_filter": geospatial_filter,
            "bbox": bbox,
        }
        if radius_m is not None:
            payload_data["radius_m"] = radius_m
        if image_width is not None:
            payload_data["image_width"] = image_width
        if image_height is not None:
            payload_data["image_height"] = image_height
        if image_crs is not None:
            payload_data["image_crs"] = image_crs
        if image_format is not None:
            payload_data["image_format"] = image_format
        payload = await asyncio.to_thread(
            LocationSearchRequest.model_validate, payload_data
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.errors(),
        ) from exc

    response_payload = await process_location_search(payload)
    serialized_payload = await asyncio.to_thread(jsonable_encoder, response_payload)
    return JSONResponse(content=serialized_payload)


###############################################################################
@router.post("/agentic", status_code=status.HTTP_202_ACCEPTED)
async def search_by_agent() -> dict[str, str]:
    return {"message": "Agentic search endpoint is not implemented yet."}
