from __future__ import annotations

import base64
import json
import math
import os
from binascii import Error as BinasciiError
from datetime import date, datetime, time
from dataclasses import dataclass
from typing import Any, Final

import httpx

from AEGIS.app.constants import (
    GEO_AGENTIC_URL, 
    GEO_SEARCH_URL,
    API_BASE_URL,
    HTTP_TIMEOUT_SECONDS,   
    DEFAULT_TIMELINE_BACKTRACK,
    SURROUNDING_RANGE,
    MIN_YEAR,
    DEFAULT_AGENTIC_TEMPERATURE,
    MIN_AGENTIC_TEMPERATURE,
    MAX_AGENTIC_TEMPERATURE,
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
            "latitude": ComponentState(value=None, enabled=True),
            "longitude": ComponentState(value=None, enabled=True),
        }

    return {
        "country": ComponentState(enabled=True),
        "city": ComponentState(enabled=True),
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
            "use_coordinates": ComponentState(value=use_coordinates, enabled=False),
            "latitude": ComponentState(enabled=False),
            "longitude": ComponentState(enabled=False),
            "date": ComponentState(enabled=False),
            "timeline": ComponentState(enabled=False),
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
        latitude_state = ComponentState(enabled=True)
        longitude_state = ComponentState(enabled=True)
    else:
        country_state = ComponentState(enabled=True)
        city_state = ComponentState(enabled=True)
        latitude_state = ComponentState(value=None, enabled=False)
        longitude_state = ComponentState(value=None, enabled=False)

    return {
        "filter": ComponentState(enabled=True),
        "country": country_state,
        "city": city_state,
        "use_coordinates": ComponentState(enabled=True),
        "latitude": latitude_state,
        "longitude": longitude_state,
        "date": ComponentState(enabled=True),
        "timeline": ComponentState(enabled=True),
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
async def load_default_map_image(
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
    target_moment: str | date | datetime | None,
    timeline_year: int | float | None,
) -> tuple[bytes | str | None, str]:
    payload, error_message = build_request_payload(
        filter_name=filter_name,
        country=country,
        city=city,
        use_coordinates=use_coordinates,
        latitude=latitude,
        longitude=longitude,
        target_moment=target_moment,
        timeline_year=timeline_year,
    )
    if error_message:
        return None, error_message
    return await execute_map_request(GEO_SEARCH_URL, payload)


###############################################################################
async def load_agentic_map_image(
    llm_query: str | None,
    use_cloud_models: bool,
    openai_model: str | None,
    agent_model: str | None,
    temperature: float | int | None,
) -> tuple[bytes | str | None, str]:
    payload, error_message = build_agentic_request_payload(
        query=llm_query,
        use_cloud_models=use_cloud_models,
        openai_model=openai_model,
        agent_model=agent_model,
        temperature=temperature,
    )
    if error_message:
        return None, error_message
    return await execute_map_request(GEO_AGENTIC_URL, payload)


###############################################################################
async def execute_map_request(
    endpoint: str, payload: dict[str, Any]
) -> tuple[bytes | str | None, str]:
    try:
        async with httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(endpoint, json=payload)
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

    image_value, message = coerce_image_value(data)
    if image_value is None:
        detail = message or data.get("detail") or data.get("message")
        return None, f"[ERROR] {detail or 'No imagery available.'}"

    status_message = message or data.get("message") or data.get("detail")
    if not status_message:
        status_message = "Map imagery loaded successfully."

    return image_value, status_message


###############################################################################
def build_request_payload(
    *,
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
    target_moment: str | date | datetime | None,
    timeline_year: int | float | None,
) -> tuple[dict[str, Any], str | None]:
    payload: dict[str, Any] = {}
    if filter_name:
        payload["filter"] = filter_name

    if use_coordinates:
        if latitude is None or longitude is None:
            return {}, "[ERROR] Provide both latitude and longitude to use coordinates."
        payload["coordinates"] = {"latitude": latitude, "longitude": longitude}
    else:
        if not country and not city:
            return {}, "[ERROR] Specify at least a country or a city to locate the map."
        payload["location"] = {
            "country": country or None,
            "city": city or None,
        }

    temporal_payload = build_temporal_payload(
        target_moment=target_moment,
        timeline_year=timeline_year,
        use_coordinates=use_coordinates,
    )
    payload.update(temporal_payload)
    return payload, None


###############################################################################
def build_agentic_request_payload(
    *,
    query: str | None,
    use_cloud_models: bool,
    openai_model: str | None,
    agent_model: str | None,
    temperature: float | int | None,
) -> tuple[dict[str, Any], str | None]:
    prompt = (query or "").strip()
    if not prompt:
        return {}, "[ERROR] Provide a prompt for agentic search."

    agent_candidate = (agent_model or "").strip()
    if not agent_candidate:
        return {}, "[ERROR] Select an agent model before running agentic search."

    payload: dict[str, Any] = {
        "query": prompt,
        "agent_model": agent_candidate,
        "use_cloud_models": bool(use_cloud_models),
        "temperature": sanitize_temperature(temperature),
    }

    if payload["use_cloud_models"]:
        provider_model = (openai_model or "").strip()
        if not provider_model:
            return {}, "[ERROR] Choose an OpenAI model when cloud models are enabled."
        payload["openai_model"] = provider_model
    else:
        payload["openai_model"] = None

    return payload, None


###############################################################################
def sanitize_temperature(value: float | int | None) -> float:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return DEFAULT_AGENTIC_TEMPERATURE
    temperature = float(value)
    if temperature < MIN_AGENTIC_TEMPERATURE:
        return MIN_AGENTIC_TEMPERATURE
    if temperature > MAX_AGENTIC_TEMPERATURE:
        return MAX_AGENTIC_TEMPERATURE
    return temperature


###############################################################################
def build_temporal_payload(
    *,
    target_moment: str | date | datetime | None,
    timeline_year: int | float | None,
    use_coordinates: bool,
) -> dict[str, Any]:
    parsed_datetime = parse_datetime_value(target_moment)
    parsed_date = parse_date_value(target_moment)
    parsed_time = parsed_datetime.timetz() if parsed_datetime else None
    timeline = coerce_timeline_year(parsed_date, timeline_year)
    payload: dict[str, Any] = {
        "temporal": {
            "timeline_year": timeline,
            "reference_date": parsed_date.isoformat() if parsed_date else None,
            "time_of_day": parsed_time.isoformat() if parsed_time else None,
        }
    }
    payload["mode"] = "coordinates" if use_coordinates else "search"
    return payload


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
def coerce_timeline_year(parsed_date: date | None, candidate: int | float | None) -> int:
    today_year = date.today().year
    if parsed_date is None:
        min_year = max(today_year - DEFAULT_TIMELINE_BACKTRACK, MIN_YEAR)
        max_year = today_year
        value = today_year
    else:
        base_year = parsed_date.year
        min_year = max(base_year - SURROUNDING_RANGE, MIN_YEAR)
        max_year = min(base_year + SURROUNDING_RANGE, today_year)
        if min_year > max_year:
            min_year, max_year = max_year, min_year
        value = base_year
    if isinstance(candidate, (int, float)):
        candidate_int = int(candidate)
        if candidate_int < min_year:
            return min_year
        if candidate_int > max_year:
            return max_year
        return candidate_int
    return int(value)


###############################################################################
def adjust_timeline_slider(target_date: str | date | datetime | None) -> ComponentState:
    parsed_date = parse_date_value(target_date)
    today_year = date.today().year
    if parsed_date is None:
        minimum = max(today_year - DEFAULT_TIMELINE_BACKTRACK, MIN_YEAR)
        maximum = today_year
        value = today_year
    else:
        base_year = parsed_date.year
        minimum = max(base_year - SURROUNDING_RANGE, MIN_YEAR)
        maximum = min(base_year + SURROUNDING_RANGE, today_year)
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        value = min(max(base_year, minimum), maximum)
    return ComponentState(minimum=minimum, maximum=maximum, value=value)


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
def coerce_image_value(payload: dict[str, Any]) -> tuple[bytes | str | None, str]:
    message = ""
    image_value: bytes | str | None = None

    image_section = payload.get("image")
    if isinstance(image_section, dict):
        message = coerce_message(image_section)
        image_value = extract_image_from_dict(image_section)

    if image_value is None:
        if isinstance(payload.get("image_url"), str):
            image_value = payload["image_url"]
        elif isinstance(payload.get("animation_url"), str):
            image_value = payload["animation_url"]
        elif isinstance(payload.get("image_base64"), str):
            image_value = decode_base64(payload["image_base64"])
        elif isinstance(payload.get("image_data"), str):
            image_value = decode_base64(payload["image_data"])
        elif isinstance(payload.get("image"), str):
            decoded = decode_base64(payload["image"])
            image_value = decoded if decoded is not None else payload["image"]

    if image_value is None:
        frames = payload.get("frames")
        if isinstance(frames, list):
            for frame in frames:
                if isinstance(frame, str):
                    candidate = decode_base64(frame)
                    if candidate is not None:
                        image_value = candidate
                        break

    if not message:
        message = coerce_message(payload)

    return image_value, message


###############################################################################
def extract_image_from_dict(data: dict[str, Any]) -> bytes | str | None:
    if isinstance(data.get("url"), str):
        return data["url"]
    base64_candidate = data.get("base64") or data.get("data")
    if isinstance(base64_candidate, str):
        decoded = decode_base64(base64_candidate)
        if decoded is not None:
            return decoded
        return base64_candidate
    return None


###############################################################################
def coerce_message(data: dict[str, Any]) -> str:
    for key in ("caption", "message", "detail", "status"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


###############################################################################
def decode_base64(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (ValueError, BinasciiError):
        return None
