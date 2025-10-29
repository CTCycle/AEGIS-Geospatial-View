from __future__ import annotations

import json
from datetime import date, datetime, time
from dataclasses import dataclass
from typing import Any

import httpx

from AEGIS.app.configurations import ClientRuntimeConfig
from AEGIS.app.constants import (
    API_BASE_URL,
    GEO_SEARCH_URL,
    HTTP_TIMEOUT_SECONDS,
)

runtime_config = ClientRuntimeConfig()

###############################################################################
MISSING = object()


###############################################################################
@dataclass
class ComponentUpdate:
    value: Any = MISSING
    enabled: bool | None = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    visible: bool | None = None


###############################################################################
def set_location_mode(use_coordinates: bool) -> dict[str, ComponentUpdate]:
    if use_coordinates:
        return {
            "country": ComponentUpdate(value=None, enabled=False),
            "city": ComponentUpdate(value="", enabled=False),
            "address": ComponentUpdate(value="", enabled=False),
            "latitude": ComponentUpdate(value=None, enabled=True),
            "longitude": ComponentUpdate(value=None, enabled=True),
        }

    return {
        "country": ComponentUpdate(enabled=True),
        "city": ComponentUpdate(enabled=True),
        "address": ComponentUpdate(enabled=True),
        "latitude": ComponentUpdate(value=None, enabled=False),
        "longitude": ComponentUpdate(value=None, enabled=False),
    }


###############################################################################
def set_agentic_mode(
    agentic_enabled: bool, use_coordinates: bool
) -> dict[str, ComponentUpdate]:
    if agentic_enabled:
        openai_enabled = runtime_config.default_use_cloud
        openai_default = (
            runtime_config.openai_model_choices[0]
            if openai_enabled and runtime_config.openai_model_choices
            else None
        )
        return {
            "filter": ComponentUpdate(enabled=False),
            "country": ComponentUpdate(enabled=False),
            "city": ComponentUpdate(enabled=False),
            "address": ComponentUpdate(enabled=False),
            "use_coordinates": ComponentUpdate(value=use_coordinates, enabled=False),
            "latitude": ComponentUpdate(enabled=False),
            "longitude": ComponentUpdate(enabled=False),
            "date": ComponentUpdate(enabled=False),
            "llm_query": ComponentUpdate(enabled=True),
            "use_cloud": ComponentUpdate(
                value=openai_enabled,
                enabled=True,
            ),
            "openai_model": ComponentUpdate(
                value=openai_default,
                enabled=openai_enabled,
            ),
            "agent_model": ComponentUpdate(enabled=True),
            "temperature": ComponentUpdate(
                enabled=True,
                minimum=runtime_config.agentic_temperature_min,
                maximum=runtime_config.agentic_temperature_max,
            ),
            "search": ComponentUpdate(enabled=False),
            "agentic": ComponentUpdate(enabled=True),
        }

    if use_coordinates:
        country_state = ComponentUpdate(enabled=False)
        city_state = ComponentUpdate(enabled=False)
        address_state = ComponentUpdate(enabled=False)
        latitude_state = ComponentUpdate(enabled=True)
        longitude_state = ComponentUpdate(enabled=True)
    else:
        country_state = ComponentUpdate(enabled=True)
        city_state = ComponentUpdate(enabled=True)
        address_state = ComponentUpdate(enabled=True)
        latitude_state = ComponentUpdate(value=None, enabled=False)
        longitude_state = ComponentUpdate(value=None, enabled=False)

    return {
        "filter": ComponentUpdate(enabled=True),
        "country": country_state,
        "city": city_state,
        "address": address_state,
        "use_coordinates": ComponentUpdate(enabled=True),
        "latitude": latitude_state,
        "longitude": longitude_state,
        "date": ComponentUpdate(enabled=True),
        "llm_query": ComponentUpdate(enabled=False),
        "use_cloud": ComponentUpdate(value=False, enabled=False),
        "openai_model": ComponentUpdate(value=None, enabled=False),
        "agent_model": ComponentUpdate(enabled=False),
        "temperature": ComponentUpdate(
            value=runtime_config.agentic_temperature_default,
            enabled=False,
            minimum=runtime_config.agentic_temperature_min,
            maximum=runtime_config.agentic_temperature_max,
        ),
        "search": ComponentUpdate(enabled=True),
        "agentic": ComponentUpdate(enabled=False),
    }


###############################################################################
def set_cloud_model_mode(use_cloud: bool) -> ComponentUpdate:
    if use_cloud:
        default_model = (
            runtime_config.openai_model_choices[0]
            if runtime_config.openai_model_choices
            else None
        )
        return ComponentUpdate(value=default_model, enabled=True)
    return ComponentUpdate(value=None, enabled=False)


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
    if isinstance(value, date) and not isinstance(value, datetime):
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
    for key in ("status_message", "message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Map search request submitted."
