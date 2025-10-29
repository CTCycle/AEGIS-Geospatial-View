from __future__ import annotations

import json
from datetime import date, datetime, time
from dataclasses import dataclass
from typing import Any, Final

import httpx

from AEGIS.app.constants import (
    API_BASE_URL,
    GEO_SEARCH_URL,
    HTTP_TIMEOUT_SECONDS,
    DEFAULT_AGENTIC_TEMPERATURE,
)

NO_UPDATE: Final = object()

@dataclass
class ComponentState:
    value: Any = NO_UPDATE
    enabled: bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None


###############################################################################
def set_location_mode(use_coordinates: bool) -> dict[str, ComponentState]:
    if use_coordinates:
        return {
            "country": ComponentState(value=None, enabled=False),
            "city": ComponentState(value="", enabled=False),
            "address": ComponentState(value="", enabled=False),
            "latitude": ComponentState(value=None, enabled=True),
            "longitude": ComponentState(value=None, enabled=True),
        }

    return {
        "country": ComponentState(enabled=True),
        "city": ComponentState(enabled=True),
        "address": ComponentState(enabled=True),
        "latitude": ComponentState(value=None, enabled=False),
        "longitude": ComponentState(value=None, enabled=False),
    }


###############################################################################
def set_agentic_mode(
    agentic_enabled: bool, use_coordinates: bool
) -> dict[str, ComponentState]:
    if agentic_enabled:
        return {
            "filter": ComponentState(enabled=False),
            "country": ComponentState(enabled=False),
            "city": ComponentState(enabled=False),
            "address": ComponentState(enabled=False),
            "use_coordinates": ComponentState(value=use_coordinates, enabled=False),
            "latitude": ComponentState(enabled=False),
            "longitude": ComponentState(enabled=False),
            "date": ComponentState(enabled=False),
            "llm_query": ComponentState(enabled=True),
            "use_cloud": ComponentState(enabled=True),
            "openai_model": ComponentState(enabled=False),
            "agent_model": ComponentState(enabled=True),
            "temperature": ComponentState(enabled=True),
            "search": ComponentState(enabled=False),
            "agentic": ComponentState(enabled=True),
        }

    if use_coordinates:
        country_state = ComponentState(enabled=False)
        city_state = ComponentState(enabled=False)
        address_state = ComponentState(enabled=False)
        latitude_state = ComponentState(enabled=True)
        longitude_state = ComponentState(enabled=True)
    else:
        country_state = ComponentState(enabled=True)
        city_state = ComponentState(enabled=True)
        address_state = ComponentState(enabled=True)
        latitude_state = ComponentState(value=None, enabled=False)
        longitude_state = ComponentState(value=None, enabled=False)

    return {
        "filter": ComponentState(enabled=True),
        "country": country_state,
        "city": city_state,
        "address": address_state,
        "use_coordinates": ComponentState(enabled=True),
        "latitude": latitude_state,
        "longitude": longitude_state,
        "date": ComponentState(enabled=True),
        "llm_query": ComponentState(enabled=False),
        "use_cloud": ComponentState(value=False, enabled=False),
        "openai_model": ComponentState(value=None, enabled=False),
        "agent_model": ComponentState(enabled=False),
        "temperature": ComponentState(value=DEFAULT_AGENTIC_TEMPERATURE, enabled=False),
        "search": ComponentState(enabled=True),
        "agentic": ComponentState(enabled=False),
    }


###############################################################################
def set_cloud_model_mode(use_cloud: bool) -> ComponentState:
    if use_cloud:
        return ComponentState(enabled=True)
    return ComponentState(value=None, enabled=False)


###############################################################################
def sanitize_text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


###############################################################################
def extract_coordinates(parameters: dict[str, Any]) -> tuple[float | None, float | None]:
    latitude = parameters.get("latitude")
    longitude = parameters.get("longitude")
    coordinates = parameters.get("coordinates")
    if isinstance(coordinates, dict):
        latitude = coordinates.get("latitude", latitude)
        longitude = coordinates.get("longitude", longitude)
    return coerce_float(latitude), coerce_float(longitude)


###############################################################################
def coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


###############################################################################
async def submit_location_search(
    parameters: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    payload, error_message = build_request_payload(parameters)
    if error_message:
        return None, error_message
    return await search_maps(payload)


###############################################################################
async def search_maps(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(GEO_SEARCH_URL, json=payload)
        response.raise_for_status()
    except httpx.RequestError as exc:
        return None, f"[ERROR] Unable to reach map service: {exc}"
    except httpx.HTTPStatusError as exc:
        detail = extract_error_detail(exc.response)
        return None, f"[ERROR] Map service error {exc.response.status_code}: {detail}"

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return None, f"[ERROR] Invalid response received from map service: {exc}"

    if not isinstance(data, dict):
        return None, "[ERROR] Map service returned an unexpected payload."

    status_message = extract_status_message(data)
    if not status_message:
        status_message = "Map search request submitted."

    formatted_status = (
        f"Endpoint: {GEO_SEARCH_URL}\nStatus: {status_message.strip()}"
    )

    return data, formatted_status


###############################################################################
def build_request_payload(parameters: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    filter_name = sanitize_text(parameters.get("filter"))
    country = sanitize_text(parameters.get("country"))
    city = sanitize_text(parameters.get("city"))
    address = sanitize_text(parameters.get("address"))
    use_coordinates = bool(parameters.get("use_coordinates"))
    latitude, longitude = extract_coordinates(parameters)

    payload: dict[str, Any] = {
        "use_coordinates": use_coordinates,
        "mode": "coordinates" if use_coordinates else "search",
    }

    if filter_name:
        payload["filter"] = filter_name

    if use_coordinates:
        if latitude is None or longitude is None:
            return {}, "[ERROR] Provide both latitude and longitude to use coordinates."
        payload["latitude"] = latitude
        payload["longitude"] = longitude
    else:
        if not address:
            return {}, "[ERROR] Provide an address to locate the map."
        payload["address"] = address
        if country:
            payload["country"] = country
        if city:
            payload["city"] = city

    temporal_payload = build_temporal_payload(
        target_moment=parameters.get("datetime") or parameters.get("date"),
    )
    payload.update(temporal_payload)
    return payload, None


###############################################################################
def build_temporal_payload(
    *,
    target_moment: str | date | datetime | None,
) -> dict[str, Any]:
    parsed_datetime = parse_datetime_value(target_moment)
    parsed_date = parse_date_value(target_moment)
    if parsed_datetime and parsed_date is None:
        parsed_date = parsed_datetime.date()
    parsed_time = parsed_datetime.timetz() if parsed_datetime else None
    return {
        "datetime": parsed_datetime.isoformat() if parsed_datetime else None,
        "reference_date": parsed_date.isoformat() if parsed_date else None,
        "time_of_day": parsed_time.isoformat() if parsed_time else None,
    }


###############################################################################
def parse_date_value(value: str | date | datetime | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        try:
            return date.fromisoformat(candidate)
        except ValueError:
            try:
                normalized = candidate.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized).date()
            except ValueError:
                return None
    return None


###############################################################################
def parse_datetime_value(value: str | date | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        normalized = candidate.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            try:
                return datetime.fromisoformat(f"{normalized}T00:00:00")
            except ValueError:
                return None
    return None


###############################################################################
def extract_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except json.JSONDecodeError:
        return response.text.strip() or "Unexpected error"

    if isinstance(data, dict):
        detail = data.get("detail") or data.get("message")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    return "Unexpected error"


###############################################################################
def extract_status_message(data: dict[str, Any]) -> str:
    for key in ("message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
