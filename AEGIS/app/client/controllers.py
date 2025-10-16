from __future__ import annotations

import base64
import json
import os
from binascii import Error as BinasciiError
from datetime import date, datetime, time
from typing import Any

import httpx
from gradio import update as gr_update

from AEGIS.app.constants import GEO_API_URL

_API_BASE_URL = os.getenv("AEGIS_API_BASE_URL", "http://127.0.0.1:8000")
_HTTP_TIMEOUT_SECONDS = 30.0
_DEFAULT_TIMELINE_BACKTRACK = 20
_SURROUNDING_RANGE = 10
_MIN_YEAR = 1900


###############################################################################
def set_location_mode(use_coordinates: bool) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    if use_coordinates:
        return (
            gr_update(value=None, interactive=False),
            gr_update(value="", interactive=False),
            gr_update(value=None, interactive=True),
            gr_update(value=None, interactive=True),
        )

    return (
        gr_update(interactive=True),
        gr_update(interactive=True),
        gr_update(value=None, interactive=False),
        gr_update(value=None, interactive=False),
    )


###############################################################################
def set_agentic_mode(
    agentic_enabled: bool, use_coordinates: bool
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
    dict[str, Any],
]:
    if agentic_enabled:
        return (
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(value=use_coordinates, interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=False),
            gr_update(interactive=True),
        )

    if use_coordinates:
        country_update = gr_update(interactive=False)
        city_update = gr_update(interactive=False)
        latitude_update = gr_update(interactive=True)
        longitude_update = gr_update(interactive=True)
    else:
        country_update = gr_update(interactive=True)
        city_update = gr_update(interactive=True)
        latitude_update = gr_update(interactive=False)
        longitude_update = gr_update(interactive=False)

    return (
        gr_update(interactive=True),
        country_update,
        city_update,
        gr_update(interactive=True),
        latitude_update,
        longitude_update,
        gr_update(interactive=True),
        gr_update(interactive=True),
        gr_update(interactive=True),
        gr_update(interactive=False),
    )


###############################################################################
async def load_map_image(
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
    target_date: str | date | None,
    target_time: str | time | None,
    timeline_year: int | float | None,
    agentic_search: bool,
    llm_query: str | None,
) -> tuple[dict[str, Any], str]:
    if agentic_search:
        prompt = (llm_query or "").strip()
        if not prompt:
            return gr_update(value=None), "[ERROR] Provide a prompt for agentic search."
        payload = {"mode": "agentic", "query": prompt}
    else:
        payload, error_message = build_request_payload(
            filter_name=filter_name,
            country=country,
            city=city,
            use_coordinates=use_coordinates,
            latitude=latitude,
            longitude=longitude,
            target_date=target_date,
            target_time=target_time,
            timeline_year=timeline_year,
        )
        if error_message:
            return gr_update(value=None), error_message

    try:
        async with httpx.AsyncClient(
            base_url=_API_BASE_URL, timeout=_HTTP_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(GEO_API_URL, json=payload)
        response.raise_for_status()
    except httpx.RequestError as exc:
        return gr_update(value=None), f"[ERROR] Unable to reach map service: {exc}"
    except httpx.HTTPStatusError as exc:
        detail = extract_error_detail(exc.response)
        return (
            gr_update(value=None),
            f"[ERROR] Map service error {exc.response.status_code}: {detail}",
        )

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        return (
            gr_update(value=None),
            f"[ERROR] Invalid response received from map service: {exc}",
        )

    if not isinstance(data, dict):
        return gr_update(value=None), "[ERROR] Map service returned an unexpected payload."

    image_value, message = coerce_image_value(data)
    if image_value is None:
        detail = message or data.get("detail") or data.get("message")
        return gr_update(value=None), f"[ERROR] {detail or 'No imagery available.'}"

    status_message = message or data.get("message") or data.get("detail")
    if not status_message:
        status_message = "Map imagery loaded successfully."

    return gr_update(value=image_value), status_message


###############################################################################
def build_request_payload(
    *,
    filter_name: str | None,
    country: str | None,
    city: str | None,
    use_coordinates: bool,
    latitude: float | None,
    longitude: float | None,
    target_date: str | date | None,
    target_time: str | time | None,
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
        target_date=target_date,
        target_time=target_time,
        timeline_year=timeline_year,
        use_coordinates=use_coordinates,
    )
    payload.update(temporal_payload)
    return payload, None


###############################################################################
def build_temporal_payload(
    *,
    target_date: str | date | None,
    target_time: str | time | None,
    timeline_year: int | float | None,
    use_coordinates: bool,
) -> dict[str, Any]:
    parsed_date = parse_date_value(target_date)
    parsed_time = parse_time_value(target_time)
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
def parse_date_value(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


###############################################################################
def parse_time_value(value: str | time | None) -> time | None:
    if value is None:
        return None
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        try:
            return time.fromisoformat(value)
        except ValueError:
            return None
    return None


###############################################################################
def coerce_timeline_year(parsed_date: date | None, candidate: int | float | None) -> int:
    today_year = date.today().year
    if parsed_date is None:
        min_year = max(today_year - _DEFAULT_TIMELINE_BACKTRACK, _MIN_YEAR)
        max_year = today_year
        value = today_year
    else:
        base_year = parsed_date.year
        min_year = max(base_year - _SURROUNDING_RANGE, _MIN_YEAR)
        max_year = min(base_year + _SURROUNDING_RANGE, today_year)
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
def adjust_timeline_slider(target_date: str | date | None) -> dict[str, Any]:
    parsed_date = parse_date_value(target_date)
    today_year = date.today().year
    if parsed_date is None:
        minimum = max(today_year - _DEFAULT_TIMELINE_BACKTRACK, _MIN_YEAR)
        maximum = today_year
        value = today_year
    else:
        base_year = parsed_date.year
        minimum = max(base_year - _SURROUNDING_RANGE, _MIN_YEAR)
        maximum = min(base_year + _SURROUNDING_RANGE, today_year)
        if minimum > maximum:
            minimum, maximum = maximum, minimum
        value = min(max(base_year, minimum), maximum)
    return gr_update(minimum=minimum, maximum=maximum, value=value)


###############################################################################
def initiate_authentication() -> str:
    return "[INFO] Authentication workflow will open in a future release."


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
