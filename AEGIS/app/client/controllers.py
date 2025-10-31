from __future__ import annotations

import json
from datetime import date, datetime, time
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, status
import httpx

from AEGIS.app.utils.services.payload import coerce_float, sanitize_search_payload

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


# [HELPERS]
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

# -----------------------------------------------------------------------------
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

# -----------------------------------------------------------------------------
def set_cloud_model_mode(use_cloud: bool) -> ComponentUpdate:
    if use_cloud:
        default_model = (
            runtime_config.openai_model_choices[0]
            if runtime_config.openai_model_choices
            else None
        )
        return ComponentUpdate(value=default_model, enabled=True)
    return ComponentUpdate(value=None, enabled=False)

# -----------------------------------------------------------------------------
def extract_coordinates(parameters: dict[str, Any]) -> tuple[float | None, float | None]:
    latitude = parameters.get("latitude")
    longitude = parameters.get("longitude")
    coordinates = parameters.get("coordinates")
    if isinstance(coordinates, dict):
        latitude = coordinates.get("latitude", latitude)
        longitude = coordinates.get("longitude", longitude)
    return coerce_float(latitude), coerce_float(longitude)


###############################################################################
async def trigger_search_maps(
    url: str, payload: dict[str, Any] | None = None
) -> tuple[dict[str, Any] | None, str]:
    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json=payload)
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


# -----------------------------------------------------------------------------
def extract_status_message(data: dict[str, Any]) -> str:
    for key in ("status_message", "message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Map search request submitted."



###############################################################################
async def submit_location_search(
    filter_val: Any,
    country: str | None,
    city: str | None,
    address: str | None,
    use_coordinates: bool,
    latitude: Any,
    longitude: Any,
    date: str | None,
) -> tuple[dict[str, Any] | None, str]:
    cleaned_payload = sanitize_search_payload(
            filter_val = filter_val,
            country = country,
            city = city,
            address = address,
            use_coordinates = use_coordinates,
            latitude = latitude,
            longitude = longitude,
            date = date,
        )
    
    url = f"{API_BASE_URL}{GEO_SEARCH_URL}"
    data, message = await trigger_search_maps(url, cleaned_payload)
    normalized_message = (message or "").strip()
    return data, normalized_message



